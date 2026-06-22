import asyncio, ssl, asyncpg

DSN = "postgresql://postgres.skrauwogwxzzzavdnigs:AihDatabase2024@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"
KEYWORDS = ["invited", "recruiter", "interview", "opportunity", "your profile", "ey gds", "reached out", "interested in you"]

async def main():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(DSN, ssl=ctx)

    conditions = " OR ".join(f"lower(content) LIKE ${ i+1 }" for i in range(len(KEYWORDS)))
    params = [f"%{k}%" for k in KEYWORDS]
    rows = await conn.fetch(
        f"SELECT content FROM memory_records WHERE {conditions} ORDER BY created_at DESC LIMIT 15",
        *params,
    )
    print(f"Inbound-ish facts: {len(rows)}")
    for r in rows:
        print(" *", r["content"][:160])
    await conn.close()

asyncio.run(main())
