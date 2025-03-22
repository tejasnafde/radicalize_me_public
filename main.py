import discord
import re
import os
import asyncio
from aiohttp import web
import traceback
from discord.ext import commands
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, ValidationError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from google.generativeai.types.safety_types import HarmCategory, HarmBlockThreshold
from tools import (
    marxists_org_search,
    marxist_com_search,
    bannedthought_search,
    url_scraper,
    allowed_domains
)
KEEP_ALIVE_CHANNEL_ID = 881890878308896778
PING_INTERVAL = 9 * 60
load_dotenv()
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

client = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents
)

async def keep_alive():
    await client.wait_until_ready()
    channel = client.get_channel(KEEP_ALIVE_CHANNEL_ID)
    while not client.is_closed():
        try:
            await channel.send("🔄 Dialectical heartbeat detected")
            print("Sent keep-alive ping")
            await asyncio.sleep(PING_INTERVAL)
        except Exception as e:
            print(f"Keep-alive error: {str(e)}")
            await asyncio.sleep(60)

tools = [marxists_org_search,
    marxist_com_search,
    bannedthought_search,
    url_scraper]
class Response(BaseModel):
    topic: str = Field(description="Main topic of analysis")
    summary: str = Field(description="Detailed Marxist analysis with citations")
    #sources: list[str] = Field(description="Verified source URLs")
    tools_used: list[str] = Field(description="Tools employed in research")

    #@field_validator('sources')
    @classmethod
    def validate_sources(cls, v):
        allowed_domains = {
            'marxists.org', 'marx2mao.com', 'bannedthought.net',
            'marxist.com', 'marxistphilosophy.org', 'communist.red'
        }
        for url in v:
            if not any(d in url for d in allowed_domains):
                raise ValueError(f"Prohibited source: {url}")
        return v


llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.7,
    safety_settings={category: HarmBlockThreshold.BLOCK_NONE 
                    for category in HarmCategory},
    max_output_tokens=4000
)
parser = PydanticOutputParser(pydantic_object=Response)
system_prompt = """You are a Marxist scholar restricted to these sources:
- marxists.org 
- marx2mao.com
- bannedthought.net
- marxist.com  
- marxistphilosophy.org
- communist.red

You MUST use these tools for research:
- marxists_org_search: Search marxists.org archive
- marxist_com_search: Search Marxist.com articles
- bannedthought_search: Search BannedThought.net
- url_scraper: Fetch content from specific URLs

Provide detailed 500-1000 word analyses with:
1. Comprehensive historical context
2. Dialectical materialist analysis
3. Source contradictions examination
5. Explicitly label non-Marxist perspectives IF including due to a lack of marxist-perspective information
{format_instructions}"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{query}"),
    ("placeholder", "{agent_scratchpad}")
]).partial(format_instructions=parser.get_format_instructions())


agent = create_tool_calling_agent(
    llm=llm,
    prompt=prompt,
    tools= tools
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,  
    verbose=True,
    # handle_parsing_errors=True,
    return_intermediate_steps = True
)


def split_response(response: str) -> list[str]:
    chunks = []
    current_chunk = []
    current_length = 0
    
    paragraphs = response.split('\n\n')
    
    for para in paragraphs:
        para_length = len(para) + 2
        
        if para_length > 2000:
            sub_chunks = [para[i:i+2000] for i in range(0, len(para), 2000)]
            chunks.extend(sub_chunks)
        elif current_length + para_length > 2000:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_length = para_length
        else:
            current_chunk.append(para)
            current_length += para_length
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks

@client.event
async def on_ready():
    print("Nothing to lose but our chains")
    print("Available tools:")
    for tool in tools:
        print(f"- {tool.name}: {tool.description}")
    print("-------------------------------")
    client.loop.create_task(keep_alive())
    await web_server()

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if client.user in message.mentions:
        ctx = await client.get_context(message)
        query = re.sub(rf'<@!?{client.user.id}>', '', message.content).strip()
        
        if not query:
            return await ctx.send("Please provide a query after the mention")

        try:
            loading_msg = await ctx.send("⚙️ Analyzing class contradictions...")
            
            async with ctx.typing():
                result = await agent_executor.ainvoke({"query": query})

                if 'intermediate_steps' in result:
                    print("\nTool Usage:")
                    for step in result['intermediate_steps']:
                        tool = step[0].tool
                        input = step[0].tool_input
                        output = step[1]
                        print(f"- {tool}: {input}\n  Output: {output[:100]}...")

                raw_output = result['output']
                parsed = parser.parse(raw_output)

                # if not all(any(d in url for d in allowed_domains) for url in parsed.sources):
                #     raise ValueError("Invalid sources detected")
                response = (f"**{parsed.topic}**\n\n{parsed.summary}")
                        #   f"**Sources:**\n" + "\n".join(parsed.sources))
                
                chunks = split_response(response)

            try:
                await loading_msg.delete()
            except discord.HTTPException:
                pass

            for chunk in chunks:
                if chunk.strip():
                    await ctx.send(chunk)

        except ValidationError as e:
            await ctx.send(f"🚨 Dialectical materialist error: {str(e)}")
        except Exception as e:
            print(f"Error: {traceback.format_exc()}")
            await ctx.send(f"💥 Revolutionary process interrupted: {str(e)}")
        
        return

    await client.process_commands(message)

async def web_server():
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="Marxist bot operational"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()



client.run(DISCORD_TOKEN)
