from datetime import datetime

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from decorators import admin_required
from models.db import supabase

bp = Blueprint("admin", __name__)


@bp.route("/dashboard")
@admin_required
def dashboard():
    orders = supabase.table("orders").select("*").execute()
    data = orders.data or []
    total_orders = len(data)
    pending = len([o for o in data if o.get("status") == "pending"])
    completed = len([o for o in data if o.get("status") == "completed"])

    return render_template(
        "admin/dashboard.html",
        total_orders=total_orders,
        pending=pending,
        completed=completed,
    )


@bp.route("/suppliers")
@admin_required
def suppliers():
    data = (
        supabase.table("suppliers")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return render_template("admin/suppliers.html", suppliers=data.data or [])


@bp.route("/suppliers/add", methods=["GET", "POST"])
@admin_required
def add_supplier():
    if request.method == "POST":
        supabase.table("suppliers").insert(
            {
                "name": request.form.get("name"),
                "contact_person": request.form.get("contact_person"),
                "phone": request.form.get("phone"),
                "email": request.form.get("email"),
                "address": request.form.get("address"),
            }
        ).execute()
        flash("Thêm nhà cung cấp thành công", "success")
        return redirect(url_for("admin.suppliers"))
    return render_template("admin/supplier_form.html")


@bp.route("/products")
@admin_required
def products():
    data = supabase.table("products").select("*").execute()
    return render_template("admin/products.html", products=data.data or [])


@bp.route("/products/add", methods=["GET", "POST"])
@admin_required
def add_product():
    if request.method == "POST":
        supabase.table("products").insert(
            {
                "name": request.form.get("name"),
                "description": request.form.get("description"),
                "category": request.form.get("category"),
            }
        ).execute()
        flash("Thêm sản phẩm thành công", "success")
        return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html")


@bp.route("/products/<product_id>/suppliers", methods=["GET", "POST"])
@admin_required
def product_suppliers(product_id):
    if request.method == "POST":
        supabase.table("product_suppliers").insert(
            {
                "product_id": product_id,
                "supplier_id": request.form.get("supplier_id"),
                "cost_price": request.form.get("cost_price"),
                "sell_price": request.form.get("sell_price"),
            }
        ).execute()
        flash("Thêm nhà cung cấp cho sản phẩm thành công", "success")
    ps = (
        supabase.table("product_suppliers")
        .select("*, suppliers(name)")
        .eq("product_id", product_id)
        .execute()
    )
    suppliers = supabase.table("suppliers").select("*").execute()

    return render_template(
        "admin/product_suppliers.html",
        product_suppliers=ps.data or [],
        suppliers=suppliers.data or [],
        product_id=product_id,
    )


@bp.route("/requests")
@admin_required
def requests():
    data = (
        supabase.table("requests")
        .select("*, customers(name, phone)")
        .order("created_at", desc=True)
        .execute()
    )
    return render_template("admin/requests.html", requests=data.data or [])


@bp.route("/requests/<request_id>")
@admin_required
def request_detail(request_id):
    req = (
        supabase.table("requests")
        .select("*, customers(name, phone, address)")
        .eq("id", request_id)
        .single()
        .execute()
    )
    items = (
        supabase.table("request_items")
        .select("*, products(name, category)")
        .eq("request_id", request_id)
        .execute()
    )
    quotes = (
        supabase.table("quotes").select("*").eq("request_id", request_id).execute()
    )
    return render_template(
        "admin/request_detail.html",
        request=req.data,
        items=items.data or [],
        quotes=quotes.data or [],
    )


# ===== QUOTES (Admin báo giá) =====
@bp.route("/requests/<request_id>/quote", methods=["GET", "POST"])
@admin_required
def create_quote(request_id):
    """
    Tạo báo giá cho một request cụ thể.
    Logic form theo đặc tả: product_supplier_<product_id>, quantity_<id>, price_<id>.
    """
    if request.method == "POST":
        # Tạo quote trước với total_amount tạm thời = 0
        quote = (
            supabase.table("quotes")
            .insert(
                {
                    "request_id": request_id,
                    "admin_id": session["user"],
                    "status": "sent",
                    "total_amount": 0,
                }
            )
            .execute()
        )
        quote_id = quote.data[0]["id"]
        total = 0
        for key in request.form:
            if key.startswith("product_supplier_"):
                product_id = key.split("_")[2]
                ps_id = request.form[key]
                quantity = int(request.form.get(f"quantity_{product_id}", 0))
                price = float(request.form.get(f"price_{product_id}", 0))
                subtotal = quantity * price
                total += subtotal

                supabase.table("quote_items").insert(
                    {
                        "quote_id": quote_id,
                        "product_supplier_id": ps_id,
                        "quantity": quantity,
                        "quoted_price": price,
                        "subtotal": subtotal,
                    }
                ).execute()
        supabase.table("quotes").update({"total_amount": total}).eq(
            "id", quote_id
        ).execute()
        supabase.table("requests").update({"status": "quoted"}).eq(
            "id", request_id
        ).execute()

        flash("Báo giá thành công", "success")
        return redirect(url_for("admin.requests"))
    req_items = (
        supabase.table("request_items")
        .select("*, products(id, name)")
        .eq("request_id", request_id)
        .execute()
    )

    items_with_suppliers = []
    for item in req_items.data or []:
        ps = (
            supabase.table("product_suppliers")
            .select("*, suppliers(name)")
            .eq("product_id", item["products"]["id"])
            .eq("is_active", True)
            .execute()
        )
        items_with_suppliers.append({"item": item, "suppliers": ps.data or []})

    return render_template(
        "admin/quote_form.html",
        request_id=request_id,
        items=items_with_suppliers,
    )


@bp.route("/quotes")
@admin_required
def quotes_list():
    data = (
        supabase.table("quotes")
        .select("*, requests(customer_id)")
        .order("created_at", desc=True)
        .execute()
    )
    return render_template("admin/quotes.html", quotes=data.data or [])


@bp.route("/quotes/<quote_id>")
@admin_required
def quote_detail(quote_id):
    quote = (
        supabase.table("quotes")
        .select("*, requests(*, customers(name, phone))")
        .eq("id", quote_id)
        .single()
        .execute()
    )
    items = (
        supabase.table("quote_items")
        .select("*, product_suppliers(*, products(name), suppliers(name))")
        .eq("quote_id", quote_id)
        .execute()
    )
    return render_template(
        "admin/quote_detail.html",
        quote=quote.data,
        items=items.data or [],
    )


# ===== ORDERS =====
@bp.route("/orders")
@admin_required
def orders():
    """Danh sách đơn hàng."""
    data = (
        supabase.table("orders")
        .select("*, customers(name), suppliers(name)")
        .order("created_at", desc=True)
        .execute()
    )
    return render_template("admin/orders.html", orders=data.data or [])


@bp.route("/orders/<order_id>")
@admin_required
def order_detail(order_id):
    order = (
        supabase.table("orders")
        .select("*, customers(name, phone), suppliers(name)")
        .eq("id", order_id)
        .single()
        .execute()
    )
    items = (
        supabase.table("order_items")
        .select("*, product_suppliers(*, products(name), suppliers(name))")
        .eq("order_id", order_id)
        .execute()
    )
    payments = (
        supabase.table("customer_payments")
        .select("*")
        .eq("order_id", order_id)
        .execute()
    )
    total_paid = sum(p["amount"] for p in (payments.data or []))
    remaining = (order.data.get("total_sell") or 0) - total_paid

    return render_template(
        "admin/order_detail.html",
        order=order.data,
        items=items.data or [],
        payments=payments.data or [],
        total_paid=total_paid,
        remaining=remaining,
    )


# ===== PAYMENTS & STATUS =====
@bp.route("/orders/<order_id>/payment", methods=["POST"])
@admin_required
def add_payment(order_id):
    """Ghi nhận thanh toán từ khách hàng cho đơn hàng."""
    supabase.table("customer_payments").insert(
        {
            "order_id": order_id,
            "amount": float(request.form.get("amount", 0)),
            "payment_method": request.form.get("payment_method"),
            "note": request.form.get("note", ""),
            "created_by": session["user"],
        }
    ).execute()

    flash("Ghi nhận thanh toán thành công", "success")
    return redirect(url_for("admin.order_detail", order_id=order_id))


@bp.route("/orders/<order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    """Cập nhật trạng thái đơn hàng."""
    status = request.form.get("status")
    data = {"status": status}
    if status == "completed":
        data["completed_at"] = datetime.utcnow().isoformat()

    supabase.table("orders").update(data).eq("id", order_id).execute()
    flash("Cập nhật trạng thái thành công", "success")
    return redirect(url_for("admin.order_detail", order_id=order_id))


@bp.route("/orders/<order_id>/tracking", methods=["POST"])
@admin_required
def update_tracking(order_id):
    """Cập nhật mã vận chuyển và chuyển trạng thái sang shipping."""
    tracking_code = request.form.get("tracking_code")
    supabase.table("orders").update(
        {"tracking_code": tracking_code, "status": "shipping"}
    ).eq("id", order_id).execute()

    flash("Cập nhật mã vận chuyển thành công", "success")
    return redirect(url_for("admin.order_detail", order_id=order_id))


@bp.route("/statistics")
@admin_required
def statistics():
    """Trang thống kê doanh thu, lợi nhuận, công nợ khách hàng."""
    # Doanh thu & lợi nhuận từ đơn đã hoàn thành
    orders = (
        supabase.table("orders")
        .select("total_sell, total_cost, profit, status")
        .eq("status", "completed")
        .execute()
    )
    total_revenue = sum(o["total_sell"] for o in (orders.data or []))
    total_profit = sum(o["profit"] for o in (orders.data or []))

    # Công nợ khách hàng
    all_orders = supabase.table("orders").select("id, total_sell").execute()
    all_payments = supabase.table("customer_payments").select(
        "order_id, amount"
    ).execute()

    payments_dict = {}
    for p in all_payments.data or []:
        payments_dict[p["order_id"]] = payments_dict.get(p["order_id"], 0) + p["amount"]

    total_debt = sum(
        o["total_sell"] - payments_dict.get(o["id"], 0)
        for o in (all_orders.data or [])
    )

    return render_template(
        "admin/statistics.html",
        total_revenue=total_revenue,
        total_profit=total_profit,
        total_debt=total_debt,
    )
