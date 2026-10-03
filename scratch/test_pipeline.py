import asyncio
from app.faq_generator import IdentificationAgent

async def test_id_agent():
    agent = IdentificationAgent("TestAgent")
    url = "https://maps.app.goo.gl/RY4mb2hnf7xyBYg48"
    try:
        res = await agent.research(url)
        print("RESULT:", res)
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(test_id_agent())
