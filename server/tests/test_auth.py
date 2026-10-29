from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings


async def _request_code(client, email):
    r = await client.post("/auth/generate", json={"email": email})
    assert r.status_code == 200, r.text
    return r.json()


async def test_login_sets_httponly_cookie_and_returns_role(anon, world, sent_codes):
    data = await _request_code(anon, "Stud@X.ru")  # регистр не важен
    r = await anon.post(
        "/auth/confirm",
        json={"user_id": data["user_id"], "temporary_code_id": data["tmp_code_id"], "code": sent_codes["stud@x.ru"]},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "student"
    set_cookie = r.headers["set-cookie"]
    assert "access_token=" in set_cookie and "HttpOnly" in set_cookie
    assert (await anon.get("/basket/dish")).status_code == 200  # корзина создана при входе


async def test_unknown_email_is_404(anon, world, sent_codes):
    r = await anon.post("/auth/generate", json={"email": "nobody@x.ru"})
    assert r.status_code == 404


async def test_wrong_code_then_attempts_exhausted(anon, world, sent_codes):
    data = await _request_code(anon, "stud@x.ru")
    params = {"user_id": data["user_id"], "temporary_code_id": data["tmp_code_id"]}
    wrong = "000000" if sent_codes["stud@x.ru"] != "000000" else "111111"

    for _ in range(3):
        r = await anon.post("/auth/confirm", json={**params, "code": wrong})
        assert r.status_code == 401
        assert r.json()["detail"] == "Incorrect code"

    # четвёртая попытка блокируется, даже если код верный
    r = await anon.post("/auth/confirm", json={**params, "code": sent_codes["stud@x.ru"]})
    assert r.status_code == 429


async def test_code_is_single_use(anon, world, sent_codes):
    data = await _request_code(anon, "stud@x.ru")
    params = {"user_id": data["user_id"], "temporary_code_id": data["tmp_code_id"], "code": sent_codes["stud@x.ru"]}
    assert (await anon.post("/auth/confirm", json=params)).status_code == 200
    r = await anon.post("/auth/confirm", json=params)
    assert r.status_code == 400 and r.json()["detail"] == "Code already used"


async def test_failed_email_sending_returns_502_and_invalidates_code(anon, world, monkeypatch, caplog):
    def broken(email, code):
        raise RuntimeError(f"sensitive-provider-payload email={email} code={code}")

    monkeypatch.setattr("app.api.routers.auth.send_login_code", broken)
    r = await anon.post("/auth/generate", json={"email": "stud@x.ru"})
    assert r.status_code == 502
    assert "sensitive-provider-payload" not in caplog.text
    assert "stud@x.ru" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records if record.name == "canteen.auth")


async def test_requires_authentication(anon, world):
    assert (await anon.get("/basket/dish")).status_code == 401


async def test_expired_token_is_rejected(anon, world):
    settings = get_settings()
    token = jwt.encode(
        {"sub": "1", "role": "student", "purpose": "access", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    anon.cookies.set("access_token", f"Bearer {token}")
    assert (await anon.get("/basket/dish")).status_code == 401


async def test_token_without_expiration_is_rejected(anon, world):
    token = jwt.encode(
        {"sub": "1", "purpose": "access"}, get_settings().secret_key.get_secret_value(), algorithm="HS256"
    )
    anon.cookies.set("access_token", f"Bearer {token}")
    assert (await anon.get("/basket/dish")).status_code == 401


async def test_role_is_enforced(clients, world):
    assert (await clients.student.get("/institution/institutions")).status_code == 403
    assert (await clients.provider.get("/basket/dish")).status_code == 403
    assert (await clients.operator.post("/dishes/dish", json={"items": []})).status_code == 403


async def test_logout_clears_cookie(clients):
    r = await clients.student.post("/auth/logout")
    assert r.status_code == 200
    assert 'access_token=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]


async def test_swagger_is_disabled(anon):
    assert (await anon.get("/docs")).status_code == 404
    assert (await anon.get("/openapi.json")).status_code == 404


async def test_health_endpoint(anon):
    r = await anon.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_auth_query_parameters_are_not_accepted(anon, world, sent_codes):
    r = await anon.post("/auth/generate", params={"email": "stud@x.ru"})
    assert r.status_code == 422
    assert sent_codes == {}
    data = await _request_code(anon, "stud@x.ru")
    params = {
        "user_id": data["user_id"],
        "temporary_code_id": data["tmp_code_id"],
        "code": sent_codes["stud@x.ru"],
    }
    r = await anon.post("/auth/confirm", params=params)
    assert r.status_code == 422
    assert "access_token" not in r.cookies
    assert (await anon.post("/auth/confirm", json=params)).status_code == 200


async def test_auth_body_validation(anon, world, sent_codes):
    assert (await anon.post("/auth/generate", json={"email": "not-an-email"})).status_code == 422
    data = await _request_code(anon, "stud@x.ru")
    payload = {"user_id": data["user_id"], "temporary_code_id": data["tmp_code_id"]}
    for code in (123456, "", "12345", "1234567", "abcdef"):
        r = await anon.post("/auth/confirm", json={**payload, "code": code})
        assert r.status_code == 422


async def test_pickup_token_cannot_authenticate_as_access_token(clients):
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]
    clients.student.cookies.set("access_token", f"Bearer {token}")
    assert (await clients.student.get("/basket/dish")).status_code == 401


async def test_auth_and_pickup_responses_are_not_cached(anon, clients, sent_codes):
    responses = [
        await anon.post("/auth/generate", json={"email": "stud@x.ru"}),
        await anon.post("/auth/confirm", json={}),
        await clients.student.post("/orders/pickup_token"),
        await anon.post("/orders/pickup_token"),
        await clients.operator.post("/orders/student_order", json={"pickup_token": "invalid"}),
        await clients.operator.patch("/orders/order", json={"pickup_token": "invalid"}),
        await clients.student.post("/auth/logout"),
    ]
    for response in responses:
        assert response.headers["cache-control"] == "no-store"
