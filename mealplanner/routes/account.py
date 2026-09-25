"""Inloggen, uitloggen, eerste account en het beheer van de accounts in het huishouden."""

from http import HTTPStatus

from .. import auth
from ..web import ApiError


def register(r, app):
    db = app.db

    def status_for(req):
        return {
            "authenticated": req.user is not None,
            "user": req.user,
            "setup_required": db.count_users() == 0,
        }

    @r.get("/api/auth/status", auth=False)
    def status(req):
        return status_for(req)

    @r.post("/api/auth/setup", auth=False)
    def setup(req):
        """Het allereerste account (beheerder), alleen met de code uit het serverlog."""
        if db.count_users() > 0:
            raise ApiError(HTTPStatus.CONFLICT, "Er is al een account. Log in.")
        body = req.json()
        app.throttle.check(f"ip:{req.client_ip}")
        if not auth.same_code(body.get("code"), app.setup_code):
            app.throttle.failure(f"ip:{req.client_ip}")
            raise ApiError(HTTPStatus.FORBIDDEN, "Deze code klopt niet. Je vindt hem in het log van de server.")
        password = auth.check_new_password(body.get("password"), body.get("username"))
        user = db.create_user(body.get("username"), auth.hash_password(password), body.get("display_name"), is_admin=True)
        app.setup_code = None
        app.start_session(req, user)
        return status_for(req)

    @r.post("/api/auth/login", auth=False)
    def login(req):
        body = req.json()
        username = str(body.get("username") or "").strip().lower()[:64]
        keys = (f"ip:{req.client_ip}", f"user:{username}")
        app.throttle.check(*keys)
        user, stored = db.credentials(username)
        password = str(body.get("password") or "")[: auth.MAX_PASSWORD]
        if user is None:
            auth.dummy_verify(password)  # even lang rekenen: verraad niet of de naam bestaat
        if user is None or not auth.verify_password(password, stored):
            app.throttle.failure(*keys)
            raise auth.AuthError("Gebruikersnaam of wachtwoord klopt niet")
        app.throttle.success(*keys)
        app.start_session(req, user)
        return status_for(req)

    @r.post("/api/auth/logout", auth=False)
    def logout(req):
        app.end_session(req)
        return status_for(req)

    @r.post("/api/auth/logout-others")
    def logout_others(req):
        db.delete_user_sessions(req.user["id"], keep=req.session_hash)
        return {"ok": True}

    @r.put("/api/auth/password")
    def change_password(req):
        body = req.json()
        key = f"user:{req.user['username']}"
        app.throttle.check(key)
        if not auth.verify_password(body.get("current"), db.password_hash(req.user["id"])):
            app.throttle.failure(key)
            raise ApiError(HTTPStatus.FORBIDDEN, "Je huidige wachtwoord klopt niet")
        password = auth.check_new_password(body.get("new"), req.user["username"])
        db.set_password_hash(req.user["id"], auth.hash_password(password))
        db.delete_user_sessions(req.user["id"], keep=req.session_hash)  # andere apparaten opnieuw laten inloggen
        return {"ok": True}

    @r.put("/api/auth/profile")
    def update_profile(req):
        user = db.update_user(req.user["id"], display_name=req.json().get("display_name"))
        return {"user": user}

    # ---------- beheer (alleen beheerders) ----------

    @r.get("/api/users", admin=True)
    def list_users(req):
        return [{**u, "sessions": db.session_count(u["id"]), "me": u["id"] == req.user["id"]} for u in db.list_users()]

    @r.post("/api/users", admin=True)
    def add_user(req):
        body = req.json()
        password = auth.check_new_password(body.get("password"), body.get("username"))
        return db.create_user(
            body.get("username"), auth.hash_password(password), body.get("display_name"), bool(body.get("is_admin"))
        )

    @r.put(r"/api/users/(\d+)", admin=True)
    def update_user(req, user_id):
        user_id = int(user_id)
        body = req.json()
        if "is_admin" in body and user_id == req.user["id"] and not body["is_admin"]:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Je kunt jezelf geen beheerder-af maken")
        user = db.update_user(
            user_id,
            display_name=body.get("display_name"),
            is_admin=bool(body["is_admin"]) if "is_admin" in body else None,
        )
        if body.get("password"):
            target = db.get_user(user_id)
            password = auth.check_new_password(body["password"], target["username"])
            db.set_password_hash(user_id, auth.hash_password(password))
            db.delete_user_sessions(user_id, keep=req.session_hash if user_id == req.user["id"] else None)
        return user

    @r.delete(r"/api/users/(\d+)", admin=True)
    def delete_user(req, user_id):
        if int(user_id) == req.user["id"]:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Je kunt je eigen account niet verwijderen")
        db.delete_user(int(user_id))
        return {"ok": True}
