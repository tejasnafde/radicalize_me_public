from dotenv import load_dotenv
load_dotenv()

import discord
import re
import os
import asyncio
from aiohttp import web
import traceback
from discord.ext import commands
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ValidationError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from google.generativeai.types.safety_types import HarmCategory, HarmBlockThreshold
try:
    from typing import Annotated  # Python 3.9+
except ImportError:
    from typing_extensions import Annotated  # Fallback for older versions
from tools import (
    marxists_org_search,
    marxist_com_search,
    bannedthought_search,
    url_scraper,
    reddit_search,
    allowed_domains
)
KEEP_ALIVE_CHANNEL_ID = 881890878308896778
BOT_ID = None
PING_INTERVAL = 600

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
            msg = await channel.send("❤️")
            await msg.add_reaction('✅')
            print(f"Heartbeat sent at {datetime.now().isoformat()}")
            await asyncio.sleep(PING_INTERVAL)
        except Exception as e:
            print(f"Heartbeat error: {str(e)}")
            await asyncio.sleep(60)

tools = [marxists_org_search,
    marxist_com_search,
    bannedthought_search,
    url_scraper,
    reddit_search]
class Response(BaseModel):
    topic: str = Field(description="Main topic of analysis")
    summary: str = Field(description="Detailed Marxist analysis with citations")
    #sources: list[str] = Field(description="Verified source URLs")
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tools employed in research (marxists_org_search, marxist_com_search, etc)")

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

system_prompt = """
        You are a dialectical materialist analysis engine. Your knowledge is strictly limited to what can be verified through these tools:

        [Approved Sources]
        1. marxists.org - Primary historical documents (pre-2000)
        2. marxist.com - Contemporary Trotskyist analysis (post-2000)
        3. bannedthought.net - Active revolutionary movements
        4. communist.red - Modern Marxist theoretical developments
        5. Reddit - Proletarian perspectives from r/communism101 and related subs

        [Strict Protocol]
        1. NO PRIOR KNOWLEDGE: All assertions must derive from tool outputs
        2. TOOL MANDATE: Minimum 3 tools must be used per analysis
        3. CITATION FORMAT: [Source:ToolName] for each factual claim
        4. CONTEMPORARY LIMITS: Events after 2023 require Reddit analysis
        5. FAILURE MODE: If no sources found, state "Insufficient class analysis" 

        [Analysis Requirements]
        1. Historical context from marxists_org_search
        2. Modern context from marxist_com_search or bannedthought_search
        3. Proletarian perspective from reddit_search
        4. Direct source verification via url_scraper when quoting

        {format_instructions}

        [Anti-Hallucination Measures]
        - Uncited claims will be rejected
        - Temporal mismatches forbidden (e.g., modern analysis of pre-2000 events)
        - Non-Marxist terms must be critiqued using tool-derived material
        - Statistical claims require direct tool citations
        """

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{query}"),
    ("placeholder", "{agent_scratchpad}")
]).partial(format_instructions=parser.get_format_instructions())


try:
    agent = create_tool_calling_agent(
        llm=llm,
        prompt=prompt,
        tools=tools
    )
except Exception as e:
    print("Error binding tools:", e)
    for tool in tools:
        print(f"Tool Name: {tool.name}, Type: {type(tool)}")

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
    await web_server()
    client.loop.create_task(keep_alive())
    

@client.event
async def on_message(message):
    if message.channel.id == KEEP_ALIVE_CHANNEL_ID and message.author.id == BOT_ID:
        if message.mentions and message.mentions[0].id == BOT_ID:
            await message.add_reaction('✅')
            return
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
                print(f"printing result from agent_executor {result}")

                if 'intermediate_steps' in result:
                    print("\nTool Usage:")
                    for step in result['intermediate_steps']:
                        tool = step[0].tool
                        input = step[0].tool_input
                        output = step[1]
                        print(f"- {tool}: {input}\n  Output: {output[:100]}...")

                raw_output = result['output']
                parsed = parser.parse(raw_output)

                if not parsed.tools_used:
                    print(f"No tools used lmao ded")
                    raise ValueError("No tools were used in the analysis")

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
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"⚒️ Web server active on port {port}")



client.run(DISCORD_TOKEN)