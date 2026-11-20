
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "foodie_secret_key_123"

DB = "database.db"


def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()

    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'customer'
    );

    CREATE TABLE IF NOT EXISTS food (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        category TEXT,
        image TEXT
    );

    CREATE TABLE IF NOT EXISTS cart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        food_id INTEGER,
        quantity INTEGER DEFAULT 1,
        UNIQUE(user_id, food_id)
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        total REAL,
        status TEXT DEFAULT 'Pending'
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        food_name TEXT,
        price REAL,
        quantity INTEGER
    );
    """)

    admin = db.execute(
        "SELECT id FROM users WHERE email=?",
        ("admin@food.com",)
    ).fetchone()

    if not admin:
        db.execute(
            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
            ("Admin", "admin@food.com",
             generate_password_hash("admin123"), "admin")
        )

    count = db.execute("SELECT COUNT(*) FROM food").fetchone()[0]

    if count == 0:
        foods = [
            ("Burger", 120, "Fast Food",
             "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=500"),
            ("Pizza", 250, "Fast Food",
             "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=500"),
            ("French Fries", 90, "Snacks",
             "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=500"),
            ("Sandwich", 100, "Snacks",
             "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=500"),
            ("Pasta", 180, "Main Course",
             "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?w=500"),
            ("Ice Cream", 80, "Dessert",
             "https://images.unsplash.com/photo-1563805042-7684c019e1cb?w=500"),
            ("Coffee", 60, "Drinks",
             "https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=500"),
            ("Milkshake", 110, "Drinks",
             "https://images.unsplash.com/photo-1572490122747-3968b75cc699?w=500")
        ]

        db.executemany(
            "INSERT INTO food(name,price,category,image) VALUES(?,?,?,?)",
            foods
        )

    db.commit()
    db.close()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access only.")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/")
def index():
    db = get_db()
    foods = db.execute("SELECT * FROM food LIMIT 4").fetchall()
    db.close()
    return render_template("index.html", foods=foods)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or len(password) < 6:
            flash("Enter valid details. Password must be at least 6 characters.")
            return redirect(url_for("register"))

        db = get_db()

        try:
            db.execute(
                "INSERT INTO users(name,email,password) VALUES(?,?,?)",
                (name, email, generate_password_hash(password))
            )
            db.commit()
            flash("Registration successful. Please login.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already exists.")

        finally:
            db.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()
        db.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            flash("Welcome " + user["name"] + "!")

            if user["role"] == "admin":
                return redirect(url_for("admin"))

            return redirect(url_for("menu"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("index"))


@app.route("/menu")
def menu():
    search = request.args.get("search", "").strip()

    db = get_db()
    foods = db.execute(
        "SELECT * FROM food WHERE name LIKE ? OR category LIKE ?",
        ("%" + search + "%", "%" + search + "%")
    ).fetchall()
    db.close()

    return render_template("menu.html", foods=foods, search=search)


@app.route("/add_to_cart/<int:food_id>", methods=["POST"])
@login_required
def add_to_cart(food_id):
    db = get_db()

    food = db.execute(
        "SELECT id FROM food WHERE id=?", (food_id,)
    ).fetchone()

    if food:
        db.execute("""
            INSERT INTO cart(user_id,food_id,quantity)
            VALUES(?,?,1)
            ON CONFLICT(user_id,food_id)
            DO UPDATE SET quantity=quantity+1
        """, (session["user_id"], food_id))

        db.commit()
        flash("Food added to cart!")
    else:
        flash("Food item not found.")

    db.close()
    return redirect(url_for("menu"))


@app.route("/cart")
@login_required
def cart():
    db = get_db()

    items = db.execute("""
        SELECT cart.id, food.name, food.price, food.image,
               cart.quantity,
               food.price * cart.quantity AS subtotal
        FROM cart
        JOIN food ON cart.food_id=food.id
        WHERE cart.user_id=?
    """, (session["user_id"],)).fetchall()

    total = sum(item["subtotal"] for item in items)
    db.close()

    return render_template("cart.html", items=items, total=total)


@app.route("/update_cart/<int:cart_id>", methods=["POST"])
@login_required
def update_cart(cart_id):
    try:
        quantity = int(request.form["quantity"])
    except (ValueError, KeyError):
        flash("Invalid quantity.")
        return redirect(url_for("cart"))

    db = get_db()

    if quantity <= 0:
        db.execute(
            "DELETE FROM cart WHERE id=? AND user_id=?",
            (cart_id, session["user_id"])
        )
    elif quantity <= 50:
        db.execute(
            "UPDATE cart SET quantity=? WHERE id=? AND user_id=?",
            (quantity, cart_id, session["user_id"])
        )
    else:
        flash("Maximum quantity is 50.")

    db.commit()
    db.close()
    return redirect(url_for("cart"))


@app.route("/place_order", methods=["POST"])
@login_required
def place_order():
    db = get_db()

    items = db.execute("""
        SELECT food.name, food.price, cart.quantity
        FROM cart
        JOIN food ON cart.food_id=food.id
        WHERE cart.user_id=?
    """, (session["user_id"],)).fetchall()

    if not items:
        db.close()
        flash("Your cart is empty.")
        return redirect(url_for("cart"))

    total = sum(item["price"] * item["quantity"] for item in items)

    cursor = db.execute(
        "INSERT INTO orders(user_id,total) VALUES(?,?)",
        (session["user_id"], total)
    )

    order_id = cursor.lastrowid

    for item in items:
        db.execute("""
            INSERT INTO order_items(order_id,food_name,price,quantity)
            VALUES(?,?,?,?)
        """, (order_id, item["name"], item["price"], item["quantity"]))

    db.execute(
        "DELETE FROM cart WHERE user_id=?",
        (session["user_id"],)
    )

    db.commit()
    db.close()

    flash("Order placed successfully!")
    return redirect(url_for("orders"))


@app.route("/orders")
@login_required
def orders():
    db = get_db()

    all_orders = db.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()

    order_items = {}

    for order in all_orders:
        order_items[order["id"]] = db.execute(
            "SELECT * FROM order_items WHERE order_id=?",
            (order["id"],)
        ).fetchall()

    db.close()

    return render_template(
        "orders.html",
        orders=all_orders,
        order_items=order_items
    )


@app.route("/admin")
@login_required
@admin_required
def admin():
    db = get_db()

    foods = db.execute("SELECT * FROM food ORDER BY id DESC").fetchall()

    orders_list = db.execute("""
        SELECT orders.*, users.name, users.email
        FROM orders
        JOIN users ON orders.user_id=users.id
        ORDER BY orders.id DESC
    """).fetchall()

    customers = db.execute(
        "SELECT COUNT(*) FROM users WHERE role='customer'"
    ).fetchone()[0]

    total_orders = db.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    revenue = db.execute(
        "SELECT COALESCE(SUM(total),0) FROM orders "
        "WHERE status != 'Cancelled'"
    ).fetchone()[0]

    db.close()

    return render_template(
        "admin.html",
        foods=foods,
        orders=orders_list,
        customers=customers,
        total_orders=total_orders,
        revenue=revenue
    )


@app.route("/add_food", methods=["POST"])
@login_required
@admin_required
def add_food():
    name = request.form["name"].strip()
    category = request.form["category"].strip()
    image = request.form.get("image", "").strip()

    try:
        price = float(request.form["price"])
        if not name or not category or price <= 0:
            raise ValueError()
    except ValueError:
        flash("Enter valid food details.")
        return redirect(url_for("admin"))

    db = get_db()
    db.execute(
        "INSERT INTO food(name,price,category,image) VALUES(?,?,?,?)",
        (name, price, category, image)
    )
    db.commit()
    db.close()

    flash("Food added successfully.")
    return redirect(url_for("admin"))


@app.route("/delete_food/<int:food_id>", methods=["POST"])
@login_required
@admin_required
def delete_food(food_id):
    db = get_db()

    db.execute("DELETE FROM cart WHERE food_id=?", (food_id,))
    db.execute("DELETE FROM food WHERE id=?", (food_id,))

    db.commit()
    db.close()

    flash("Food deleted successfully.")
    return redirect(url_for("admin"))


@app.route("/update_order/<int:order_id>", methods=["POST"])
@login_required
@admin_required
def update_order(order_id):
    status = request.form["status"]

    allowed = [
        "Pending", "Preparing",
        "Out for Delivery", "Delivered", "Cancelled"
    ]

    if status not in allowed:
        flash("Invalid order status.")
        return redirect(url_for("admin"))

    db = get_db()
    db.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (status, order_id)
    )
    db.commit()
    db.close()

    flash("Order status updated.")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
