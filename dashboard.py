import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()


def get_engine():
    """Create and return a SQLAlchemy engine from DATABASE_URL."""
    url = os.getenv("DATABASE_URL")
    if not url or not url.strip():
        print("Error: DATABASE_URL is not set. Add it to your .env file.")
        return None

    try:
        engine = create_engine(url.strip())
        with engine.connect():
            pass
        return engine
    except SQLAlchemyError as exc:
        print(f"Error: failed to connect to the database: {exc}")
        return None


def store_report(engine):
    """Print counts, the catalog, and the top 3 customers."""
    with engine.connect() as conn:
        users_count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        products_count = conn.execute(text("SELECT COUNT(*) FROM products")).scalar_one()
        orders_count = conn.execute(text("SELECT COUNT(*) FROM orders")).scalar_one()

        catalog_rows = conn.execute(
            text("SELECT name, price, stock FROM products ORDER BY name")
        ).fetchall()

        top_customers = conn.execute(
            text(
                """
                SELECT u.email, COALESCE(SUM(o.quantity), 0) AS total_items
                FROM orders o
                JOIN users u ON u.id = o.user_id
                GROUP BY u.id, u.email
                ORDER BY total_items DESC, u.email ASC
                LIMIT 3
                """
            )
        ).fetchall()

    print("=== Store Dashboard ===")
    print(f"Users: {users_count} | Products: {products_count} | Orders: {orders_count}")

    print("\nCatalog:")
    for name, price, stock in catalog_rows:
        print(f"  {name:<15} ${float(price):>7.2f}   (stock {stock})")

    print("\nTop customers:")
    for email, total_items in top_customers:
        unit = "item" if int(total_items) == 1 else "items"
        print(f"  {email:<25} - {int(total_items)} {unit}")


def add_product(engine, name, category, price, stock):
    """INSERT a product and return its new id."""
    if not category or not category.strip():
        raise ValueError("Category is required and cannot be empty.")

    with engine.begin() as conn:
        new_id = conn.execute(
            text(
                """
                INSERT INTO products (name, category, price, stock)
                VALUES (:name, :category, :price, :stock)
                RETURNING id
                """
            ),
            {
                "name": name.strip(),
                "category": category.strip(),
                "price": price,
                "stock": stock,
            },
        ).scalar_one()

    return new_id


def place_order(engine, email, product_name, quantity):
    """Create an order and decrement stock in one transaction."""
    if quantity <= 0:
        raise ValueError("Quantity must be greater than 0.")

    with engine.begin() as conn:
        user_row = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email.strip()},
        ).fetchone()
        if user_row is None:
            raise ValueError(f"User with email '{email}' not found.")

        product_row = conn.execute(
            text("SELECT id, stock, price FROM products WHERE name = :name"),
            {"name": product_name.strip()},
        ).fetchone()
        if product_row is None:
            raise ValueError(f"Product '{product_name}' not found.")

        user_id = user_row.id
        product_id = product_row.id
        current_stock = int(product_row.stock)
        unit_price = product_row.price

        if current_stock < quantity:
            raise ValueError(
                f"Insufficient stock for '{product_name}': available {current_stock}, requested {quantity}."
            )

        order_row = conn.execute(
            text(
                """
                INSERT INTO orders (user_id, product_id, quantity, total_price)
                VALUES (:user_id, :product_id, :quantity, :total_price)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "product_id": product_id,
                "quantity": quantity,
                "total_price": unit_price * quantity,
            },
        ).fetchone()

        conn.execute(
            text(
                """
                UPDATE products
                SET stock = stock - :quantity
                WHERE id = :product_id AND stock >= :quantity
                """
            ),
            {
                "quantity": quantity,
                "product_id": product_id,
            },
        )

        return order_row.id if order_row else None


def prompt_add_product(engine):
    name = input("Product name: ").strip()
    category = input("Category: ").strip()
    price = float(input("Price: ").strip())
    stock = int(input("Stock: ").strip())
    new_id = add_product(engine, name, category, price, stock)
    print(f"Product created with id: {new_id}")


def prompt_place_order(engine):
    email = input("Customer email: ").strip()
    product_name = input("Product name: ").strip()
    quantity = int(input("Quantity: ").strip())
    order_id = place_order(engine, email, product_name, quantity)
    print(f"Order created (id: {order_id}) and stock updated.")


def main():
    engine = get_engine()
    if engine is None:
        sys.exit(1)

    store_report(engine)

    while True:
        print("\nActions:")
        print("  1 - Add product")
        print("  2 - Place order")
        print("  3 - Refresh report")
        print("  0 - Exit")
        choice = input("Choose an action: ").strip()

        try:
            if choice == "1":
                prompt_add_product(engine)
            elif choice == "2":
                prompt_place_order(engine)
            elif choice == "3":
                store_report(engine)
            elif choice == "0":
                break
            else:
                print("Unknown option. Please enter 1, 2, 3, or 0.")
        except (ValueError, SQLAlchemyError) as exc:
            print(f"Operation failed (rolled back): {exc}")


if __name__ == "__main__":
    main()
