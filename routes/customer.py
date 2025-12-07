from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from models.db import supabase
from decorators import login_required

bp = Blueprint("customer", __name__)


@bp.route("/dashboard")
@login_required
def dashboard():
    customer = (
        supabase.table("customers")
        .select("id")
        .eq("user_id", session["user"])
        .single()
        .execute()
    )

    customer_id = customer.data["id"]
    requests_res = (
        supabase.table("requests")
        .select("*")
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .execute()
    )
    orders_res = (
        supabase.table("orders")
        .select("*, suppliers(name)")
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .execute()
    )

    return render_template(
        "customer/dashboard.html",
        requests=requests_res.data,
        orders=orders_res.data,
    )


@bp.route("/request/new", methods=["GET", "POST"])
@login_required
def new_request():
    if request.method == "POST":
        customer = (
            supabase.table("customers")
            .select("id")
            .eq("user_id", session["user"])
            .single()
            .execute()
        )
        req = (
            supabase.table("requests")
            .insert(
                {
                    "customer_id": customer.data["id"],
                    "status": "pending",
                    "note": request.form.get("note", ""),
                }
            )
            .execute()
        )

        request_id = req.data[0]["id"]
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")

        for pid, qty in zip(product_ids, quantities):
            if pid and qty:
                supabase.table("request_items").insert(
                    {
                        "request_id": request_id,
                        "product_id": pid,
                        "quantity": int(qty),
                    }
                ).execute()

        flash("Tạo yêu cầu thành công", "success")
        return redirect(url_for("customer.dashboard"))
    products = supabase.table("products").select("*").execute()
    return render_template("customer/request_form.html", products=products.data)


@bp.route("/requests/<request_id>/quote")
@login_required
def view_quote(request_id):
    quote = (
        supabase.table("quotes")
        .select("*")
        .eq("request_id", request_id)
        .single()
        .execute()
    )

    items = (
        supabase.table("quote_items")
        .select("*, product_suppliers(*, products(name), suppliers(name))")
        .eq("quote_id", quote.data["id"])
        .execute()
    )

    return render_template(
        "customer/quote_detail.html", quote=quote.data, items=items.data
    )


@bp.route("/quotes/<quote_id>/accept", methods=["POST"])
@login_required
def accept_quote(quote_id):
    quote = (
        supabase.table("quotes")
        .select("*, request_id")
        .eq("id", quote_id)
        .single()
        .execute()
    )

    quote_items = (
        supabase.table("quote_items")
        .select("*, product_suppliers(supplier_id, cost_price)")
        .eq("quote_id", quote_id)
        .execute()
    )
    supplier_items = {}
    for item in quote_items.data:
        sid = item["product_suppliers"]["supplier_id"]
        supplier_items.setdefault(sid, []).append(item)
    req = (
        supabase.table("requests")
        .select("customer_id")
        .eq("id", quote.data["request_id"])
        .single()
        .execute()
    )
    for supplier_id, items in supplier_items.items():
        total_cost = sum(
            i["quantity"] * i["product_suppliers"]["cost_price"] for i in items
        )
        total_sell = sum(i["subtotal"] for i in items)
        profit = total_sell - total_cost

        order = (
            supabase.table("orders")
            .insert(
                {
                    "quote_id": quote_id,
                    "customer_id": req.data["customer_id"],
                    "supplier_id": supplier_id,
                    "total_cost": total_cost,
                    "total_sell": total_sell,
                    "profit": profit,
                    "status": "pending",
                }
            )
            .execute()
        )

        order_id = order.data[0]["id"]
        for item in items:
            supabase.table("order_items").insert(
                {
                    "order_id": order_id,
                    "product_supplier_id": item["product_supplier_id"],
                    "quantity": item["quantity"],
                    "cost_price": item["product_suppliers"]["cost_price"],
                    "sell_price": item["quoted_price"],
                    "subtotal": item["subtotal"],
                }
            ).execute()
    supabase.table("quotes").update({"status": "accepted"}).eq(
        "id", quote_id
    ).execute()
    supabase.table("requests").update({"status": "accepted"}).eq(
        "id", quote.data["request_id"]
    ).execute()

    flash("Đã chấp nhận báo giá. Đơn hàng đang được xử lý.", "success")
    return redirect(url_for("customer.dashboard"))


@bp.route("/orders/<order_id>")
@login_required
def order_detail(order_id):
    order = (
        supabase.table("orders")
        .select("*, suppliers(name)")
        .eq("id", order_id)
        .single()
        .execute()
    )

    items = (
        supabase.table("order_items")
        .select("*, product_suppliers(*, products(name))")
        .eq("order_id", order_id)
        .execute()
    )

    payments = (
        supabase.table("customer_payments")
        .select("*")
        .eq("order_id", order_id)
        .execute()
    )

    total_paid = sum(p["amount"] for p in payments.data)
    remaining = order.data["total_sell"] - total_paid

    return render_template(
        "customer/order_detail.html",
        order=order.data,
        items=items.data,
        total_paid=total_paid,
        remaining=remaining,
    )
