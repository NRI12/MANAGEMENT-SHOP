from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
import requests

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


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        try:
            auth_response = supabase.auth.sign_up(
                {"email": email, "password": password}
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


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        if not email:
            flash("Vui lòng nhập email.", "error")
            return render_template("auth.html", mode="forgot")

        try:
            redirect_url = Config.REDIRECT_URL
            reset_url = f"{redirect_url}/reset-password"
            supabase.auth.reset_password_email(
                email, options={"redirect_to": reset_url}
            )

            flash(
                "Nếu email tồn tại trong hệ thống, liên kết đặt lại mật khẩu đã được gửi.",
                "success",
            )
            return redirect(url_for("auth.login"))
        except Exception as e:
            flash(f"Lỗi: {str(e)}", "error")

    return render_template("auth.html", mode="forgot")


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        access_token = request.form.get("access_token", "")
        refresh_token = request.form.get("refresh_token", "")

        if not password or password != password_confirm:
            flash("Mật khẩu không khớp.", "error")
            return render_template("auth.html", mode="reset")

        if len(password) < 6:
            flash("Mật khẩu phải có ít nhất 6 ký tự.", "error")
            return render_template("auth.html", mode="reset")

        if not access_token:
            flash("Token không hợp lệ.", "error")
            return redirect(url_for("auth.forgot_password"))

        try:
            from supabase import create_client
            temp_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            temp_client.auth.set_session(
                access_token=access_token, refresh_token=refresh_token
            )
            temp_client.auth.update_user({"password": password})

            flash("Đặt lại mật khẩu thành công!", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            flash(f"Lỗi: {str(e)}", "error")
            return redirect(url_for("auth.forgot_password"))

    return render_template("auth.html", mode="reset")

@bp.route("/auth/<provider>")
def oauth_login(provider):
    """Initiate OAuth with provider"""
    # Generate state for security
    import secrets
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    
    redirect_url = f"{Config.REDIRECT_URL}/auth/callback"
    
    # Get OAuth URL from Supabase
    # For server-side Flask apps, use implicit flow (tokens in hash) instead of PKCE
    response = supabase.auth.sign_in_with_oauth({
        "provider": provider,
        "options": {
            "redirect_to": redirect_url,
            "skip_browser_redirect": False  # Let browser handle redirect for implicit flow
        }
    })
    
    if hasattr(response, 'url'):
        return redirect(response.url)
    flash("Không thể kết nối OAuth", "error")
    return redirect(url_for("auth.login"))


@bp.route("/auth/callback")
def oauth_callback():
    """Handle OAuth callback - server side processing"""
    error = request.args.get('error')
    if error:
        flash(f"Lỗi OAuth: {error}", "error")
        return redirect(url_for("auth.login"))
    
    # Try to handle code exchange directly on server side (PKCE flow)
    code = request.args.get('code')
    if code:
        try:
            print(f"DEBUG: Processing code in callback: {code}")
            
            # Exchange code using REST API directly
            exchange_url = f"{Config.SUPABASE_URL}/auth/v1/token?grant_type=authorization_code"
            headers = {
                "apikey": Config.SUPABASE_KEY,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            redirect_uri = f"{Config.REDIRECT_URL}/auth/callback"
            data = {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            }
            
            print(f"DEBUG: Exchanging code via REST API")
            response = requests.post(exchange_url, headers=headers, data=data)
            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response: {response.text}")
            
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get("access_token")
                refresh_token = token_data.get("refresh_token")
                
                if access_token:
                    # Set session and get user
                    supabase.auth.set_session(
                        access_token=access_token,
                        refresh_token=refresh_token
                    )
                    user_response = supabase.auth.get_user()
                    user = user_response.user
                else:
                    # Fallback to client-side handling
                    return render_template("auth.html", mode="oauth_callback")
            else:
                # Fallback to client-side handling if REST API fails
                print(f"DEBUG: REST API exchange failed, trying client method")
                auth_response = supabase.auth.exchange_code_for_session({"auth_code": code})
                
                if hasattr(auth_response, 'user') and auth_response.user:
                    user = auth_response.user
                elif hasattr(auth_response, 'session') and auth_response.session:
                    supabase.auth.set_session(
                        access_token=auth_response.session.access_token,
                        refresh_token=auth_response.session.refresh_token
                    )
                    user_response = supabase.auth.get_user()
                    user = user_response.user
                else:
                    # Fallback to client-side handling
                    return render_template("auth.html", mode="oauth_callback")
            
            # Check/create customer
            existing = supabase.table("customers").select("id").eq("user_id", user.id).execute()
            if not existing.data:
                metadata = user.user_metadata or {}
                name = metadata.get("full_name") or metadata.get("name") or user.email.split("@")[0]
                supabase.table("customers").insert({
                    "user_id": user.id,
                    "name": name,
                    "email": user.email,
                    "phone": metadata.get("phone", ""),
                }).execute()

            session["user"] = user.id
            session["email"] = user.email
            session["role"] = get_user_role(user.id)

            flash("Đăng nhập thành công!", "success")
            return redirect(url_for("admin.dashboard") if session["role"] == "admin" else url_for("customer.dashboard"))
            
        except Exception as e:
            import traceback
            print(f"DEBUG: Error in callback: {e}")
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            # Fallback to client-side handling
            return render_template("auth.html", mode="oauth_callback")
    
    # Nếu có hash fragment, render template để JS xử lý (implicit flow)
    return render_template("auth.html", 
                          mode="oauth_callback",
                          supabase_url=Config.SUPABASE_URL,
                          supabase_key=Config.SUPABASE_KEY)


@bp.route("/auth/complete", methods=["POST"])  
def oauth_complete():
    """Complete OAuth with code or tokens from JS"""
    code = request.form.get("code")
    access_token = request.form.get("access_token")
    refresh_token = request.form.get("refresh_token")

    try:
        # Case 1: PKCE flow - exchange code for session
        if code:
            print(f"DEBUG: Exchanging code: {code}")
            auth_response = supabase.auth.exchange_code_for_session({"auth_code": code})
            print(f"DEBUG: Exchange response: {auth_response}")
            
            if hasattr(auth_response, 'user') and auth_response.user:
                user = auth_response.user
            elif hasattr(auth_response, 'session') and auth_response.session:
                # If response has session, set it and get user
                supabase.auth.set_session(
                    access_token=auth_response.session.access_token,
                    refresh_token=auth_response.session.refresh_token
                )
                user_response = supabase.auth.get_user()
                user = user_response.user
            else:
                flash("Xác thực thất bại: không nhận được thông tin người dùng", "error")
                return redirect(url_for("auth.login"))
        
        # Case 2: Implicit flow - use tokens directly
        elif access_token:
            auth_response = supabase.auth.set_session(
                access_token=access_token,
                refresh_token=refresh_token
            )
            user = auth_response.user
        else:
            flash("Xác thực thất bại: thiếu thông tin xác thực", "error")
            return redirect(url_for("auth.login"))

        # Check/create customer
        existing = supabase.table("customers").select("id").eq("user_id", user.id).execute()
        if not existing.data:
            metadata = user.user_metadata or {}
            name = metadata.get("full_name") or metadata.get("name") or user.email.split("@")[0]
            supabase.table("customers").insert({
                "user_id": user.id,
                "name": name,
                "email": user.email,
                "phone": metadata.get("phone", ""),
            }).execute()

        session["user"] = user.id
        session["email"] = user.email
        session["role"] = get_user_role(user.id)

        flash("Đăng nhập thành công!", "success")
        return redirect(url_for("admin.dashboard") if session["role"] == "admin" else url_for("customer.dashboard"))

    except Exception as e:
        import traceback
        print(f"ERROR: {e}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        flash(f"Lỗi xác thực: {str(e)}", "error")
        return redirect(url_for("auth.login"))

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))