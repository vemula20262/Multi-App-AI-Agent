"""Real API + visible-browser rehearsal. Uses only our fictional local demo page."""

import asyncio
import json
import time
import uuid
from pathlib import Path

import httpx


async def main():
    records = []
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=90
    ) as client:
        health = (await client.get("/health")).json()
        print("Health:", json.dumps(health))
        sid, token = "smoke_" + uuid.uuid4().hex, None

        async def turn(text, decision=None):
            nonlocal token
            started = time.perf_counter()
            response = await client.post(
                "/agent/turn",
                json={
                    "session_id": sid,
                    "text": text,
                    "pending_interrupt_id": token,
                    "user_permission_granted": decision,
                },
            )
            response.raise_for_status()
            result = response.json()
            token = result["interrupt_id"]
            elapsed = round(time.perf_counter() - started, 3)
            records.append({"input": text, "seconds": elapsed, "response": result})
            print(
                f"{result['status']} / {result['action_type']} ({elapsed}s)", flush=True
            )
            return result

        first = await turn("Draft an email to Sarah")
        assert first["data"]["missing_slot"] == "topic"
        second = await turn("The project launch")
        assert second["data"]["missing_slot"] == "timeline"
        draft = await turn("Next Friday")
        assert draft["action_type"] == "DRAFT_CREATED"
        assert "Sarah" in draft["data"]["draft_content"]
        gate = await turn("Open the demo page")
        assert gate["status"] == "PERMISSION_REQUIRED", gate
        assert gate["data"]["dom_read"] is False
        denied = await turn("Deny", False)
        assert denied["action_type"] == "PERMISSION_DENIED"
        gate = await turn("Open the demo page")
        saved_token = token
        assert gate["status"] == "PERMISSION_REQUIRED"
        summary = await turn("Allow")
        assert summary["action_type"] == "BROWSER_SUMMARIZED", summary
        assert summary["data"]["characters_read"] > 100
        events = [item["event"] for item in summary["data"]["audit"]]
        assert events.index("permission_granted") < events.index("dom_read_completed")
        token = saved_token
        replay = await turn("Allow", True)
        assert replay["action_type"] == "NO_PENDING_PERMISSION"
        await turn("Cancel")
    Path(".runtime").mkdir(exist_ok=True)
    Path(".runtime/smoke-results.json").write_text(
        json.dumps({"health": health, "steps": records}, indent=2)
    )
    print(
        "PASS: slot memory, headful navigation, deny, allow, summary, replay protection."
    )


if __name__ == "__main__":
    asyncio.run(main())
