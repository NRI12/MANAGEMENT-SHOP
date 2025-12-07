from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from config import Config
from models.db import get_user_role, supabase

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        try:
            auth_response = supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )

            user = auth_response.user
            session["user"] = user.id
            session["email"] = email
            session["role"] = get_user_role(user.id)

            if session["role"] == "admin":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("customer.dashboard"))

        except Exception:
            flash("Email hoặc mật khẩu không đúng", "error")

    return render_template("auth.html", mode="login")


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        if not email:
            flash("Vui lòng nhập email.", "error")
            return render_template("auth.html", mode="forgot")

        try:
            redirect_url = current_app.config.get("REDIRECT_URL", "http://localhost:5000")
            reset_url = f"{redirect_url}/reset-password"
            supabase.auth.reset_password_email(
                email,
                options={"redirect_to": reset_url}
            )

            flash(
                "Nếu email tồn tại trong hệ thống, liên kết đặt lại mật khẩu "
                "đã được gửi. Vui lòng kiểm tra hộp thư.",
                "success",
            )
            return redirect(url_for("auth.login"))
        except Exception as e:
            flash(f"Không thể gửi email đặt lại mật khẩu: {str(e)}", "error")

    return render_template("auth.html", mode="forgot")


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        access_token = request.form.get("access_token", "")
        refresh_token = request.form.get("refresh_token", "")

        if not password or not password_confirm:
            flash("Vui lòng nhập đầy đủ thông tin.", "error")
            return render_template("auth.html", mode="reset", access_token=access_token, refresh_token=refresh_token)

        if password != password_confirm:
            flash("Mật khẩu xác nhận không khớp.", "error")
            return render_template("auth.html", mode="reset", access_token=access_token, refresh_token=refresh_token)

        if len(password) < 6:
            flash("Mật khẩu phải có ít nhất 6 ký tự.", "error")
            return render_template("auth.html", mode="reset", access_token=access_token, refresh_token=refresh_token)

        if not access_token:
            flash("Token không hợp lệ. Vui lòng yêu cầu link mới.", "error")
            return redirect(url_for("auth.forgot_password"))

        try:
            from supabase import create_client
            temp_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            auth_response = temp_client.auth.set_session(
                access_token=access_token,
                refresh_token=refresh_token
            )
            
            temp_client.auth.update_user({"password": password})

            flash("Đặt lại mật khẩu thành công! Vui lòng đăng nhập.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            flash(f"Không thể đặt lại mật khẩu: {str(e)}. Link có thể đã hết hạn.", "error")
            return redirect(url_for("auth.forgot_password"))

    return render_template("auth.html", mode="reset")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        try:
            redirect_url = current_app.config.get("REDIRECT_URL", "http://localhost:5000")
            auth_response = supabase.auth.sign_up(
                {
                    "email": email,
                    "password": password
                },
                options={"email_redirect_to": redirect_url}
            )

            user = auth_response.user
            supabase.table("customers").insert(
                {
                    "user_id": user.id,
                    "name": name,
                    "phone": phone,
                    "email": email,
                }
            ).execute()

            flash("Đăng ký thành công! Vui lòng đăng nhập.", "success")
            return redirect(url_for("auth.login"))

        except Exception as e:
            flash(f"Lỗi: {str(e)}", "error")

    return render_template("auth.html", mode="register")


@bp.route("/auth/<provider>")
def oauth_login(provider):
    redirect_url = current_app.config.get("REDIRECT_URL", "http://localhost:5000")
    callback_url = f"{redirect_url}/auth/callback"
    
    try:
        response = supabase.auth.sign_in_with_oauth({
            "provider": provider,
            "options": {
                "redirect_to": callback_url
            }
        })
        if hasattr(response, 'url') and response.url:
            return redirect(response.url)
        elif isinstance(response, dict) and 'url' in response:
            return redirect(response['url'])
        else:
            flash(f"Không thể khởi tạo đăng nhập với {provider}. Vui lòng kiểm tra cấu hình OAuth trong Supabase.", "error")
            return redirect(url_for("auth.login"))
    except Exception as e:
        flash(f"Lỗi đăng nhập với {provider}: {str(e)}", "error")
        return redirect(url_for("auth.login"))


@bp.route("/auth/callback", methods=["GET", "POST"])
def oauth_callback():
    code = request.args.get("code")
    if request.method == "POST":
        access_token = request.form.get("access_token")
        refresh_token = request.form.get("refresh_token")
        
        if access_token:
            try:
                auth_response = supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=refresh_token
                )
                return _handle_oauth_user(auth_response.user, is_new_user=False)
            except Exception as e:
                flash(f"Lỗi xác thực: {str(e)}", "error")
                return redirect(url_for("auth.login"))
    if code:
        try:
            redirect_url = current_app.config.get("REDIRECT_URL", "http://localhost:5000")
            callback_url = f"{redirect_url}/auth/callback"
            import httpx
            exchange_url = f"{Config.SUPABASE_URL}/auth/v1/token"
            try:
                headers = {
                    "apikey": Config.SUPABASE_KEY,
                    "Content-Type": "application/json"
                }
                json_data = {
                    "code": code,
                    "redirect_to": callback_url
                }
                
                response = httpx.post(
                    exchange_url,
                    json=json_data,
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    form_data = {
                        "code": code,
                        "redirect_to": callback_url
                    }
                    
                    response = httpx.post(
                        exchange_url,
                        data=form_data,
                        headers=headers,
                        timeout=10.0
                    )
                print(f"OAuth Exchange Response: Status {response.status_code}")
                if response.status_code != 200:
                    print(f"Error Response: {response.text}")
                if response.status_code == 200:
                    tokens = response.json()
                    access_token = tokens.get("access_token")
                    refresh_token = tokens.get("refresh_token")
                    if access_token:
                        auth_response = supabase.auth.set_session(
                            access_token=access_token,
                            refresh_token=refresh_token
                        )
                        
                        user = auth_response.user
                        return _handle_oauth_user(user, is_new_user=True)
                    else:
                        flash("Không thể lấy token từ code. Vui lòng thử lại.", "error")
                        return redirect(url_for("auth.login"))
                else:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("msg") or error_data.get("error_description") or error_data.get("error") or response.text[:150]
                    except:
                        error_msg = response.text[:150] if hasattr(response, 'text') else f"Status {response.status_code}"
                    
                    print(f"OAuth Exchange Failed: {error_msg}")
                    flash(f"Lỗi xác thực: {error_msg}. Vui lòng kiểm tra Redirect URL trong Supabase Dashboard phải là: {callback_url}", "error")
                    return redirect(url_for("auth.login"))
                    
            except httpx.RequestError as e:
                print(f"OAuth Request Error: {str(e)}")
                flash(f"Lỗi kết nối đến Supabase: {str(e)}", "error")
                return redirect(url_for("auth.login"))
            
        except Exception as e:
            import traceback
            print(f"OAuth Callback Error: {str(e)}")
            print(traceback.format_exc())
            flash(f"Lỗi xác thực: {str(e)}", "error")
            return redirect(url_for("auth.login"))
    return render_template("auth.html", mode="oauth_callback")


def _handle_oauth_user(user, is_new_user=False):
    try:
        existing_customer = (
            supabase.table("customers")
            .select("id")
            .eq("user_id", user.id)
            .execute()
        )
        if not existing_customer.data:
            user_metadata = user.user_metadata or {}
            name = (
                user_metadata.get("full_name") or 
                user_metadata.get("name") or 
                user_metadata.get("display_name") or
                (user_metadata.get("first_name", "") + " " + user_metadata.get("last_name", "")).strip() or
                (user.email or "").split("@")[0] if user.email else "User"
            )
            supabase.table("customers").insert({
                "user_id": user.id,
                "name": name,
                "email": user.email or "",
                "phone": user_metadata.get("phone", ""),
            }).execute()
            
            message = "Đăng ký và đăng nhập thành công!"
        else:
            message = "Đăng nhập thành công!"
        session["user"] = user.id
        session["email"] = user.email or ""
        session["role"] = get_user_role(user.id)
        
        flash(message, "success")
        
        if session["role"] == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("customer.dashboard"))
        
    except Exception as e:
        flash(f"Lỗi xử lý tài khoản: {str(e)}", "error")
        return redirect(url_for("auth.login"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


