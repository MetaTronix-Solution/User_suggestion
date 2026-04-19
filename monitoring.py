import time
from fastapi import Request
from datetime import datetime, timezone

# Optional DB logging
def log_system_metric(path, method, response_ms, status):
    try:
        from unified import get_db_connection  # import here to avoid circular import
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO system_metrics (path, method, response_ms, status)
            VALUES (%s, %s, %s, %s)
        """, (path, method, response_ms, status))

        conn.commit()
        cur.close()
        conn.close()
    except:
        pass


# Middleware function
async def monitor_requests(request: Request, call_next):
    start_time = time.time()

    try:
        response = await call_next(request)

        response_time = int((time.time() - start_time) * 1000)

        print(f"[{request.method}] {request.url.path} → {response_time}ms")

        # Save to DB (optional)
        log_system_metric(request.url.path, request.method, response_time, response.status_code)

        return response

    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)

        print(f"[ERROR] {request.url.path} → {response_time}ms → {e}")

        log_system_metric(request.url.path, request.method, response_time, "error")

        raise