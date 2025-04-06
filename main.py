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

import tempfile
from crawl4ai.models import CrawlResult

from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.config import Settings



from tools import (
    web_search,
    marxists_org_search,
    marxist_com_search,
    bannedthought_search,
    url_scraper,
    reddit_search
)

KEEP_ALIVE_CHANNEL_ID = 881890878308896778
BOT_ID = None
PING_INTERVAL = 600

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Add after environment variable loading
class WebContentVectorDB:
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        self.client = chromadb.PersistentClient(
            path="./marxist_db", 
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="web_content",
            embedding_function=self._embed_function
        )
    
    def _embed_function(self, texts: list[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(texts)

    def add_documents(self, results: list[CrawlResult]):
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", "?", "!", " ", ""],
        )
        
        for result in results:
            if not result.markdown_v2:
                continue
                
            docs = UnstructuredMarkdownLoader(
                file_path=tempfile.NamedTemporaryFile(
                    mode="w", 
                    suffix=".md", 
                    delete=False
                ).write(result.markdown_v2.fit_markdown)
            ).load()
            
            splits = text_splitter.split_documents(docs)
            normalized_url = self._normalize_url(result.url)
            
            self.collection.upsert(
                documents=[split.page_content for split in splits],
                metadatas=[{"source": result.url} for _ in splits],
                ids=[f"{normalized_url}_{i}" for i in range(len(splits))]
            )

    def _normalize_url(self, url):
        return url.replace("https://", "").replace("www.", "").replace("/", "_")

vector_db = WebContentVectorDB()


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

tools = [
    marxists_org_search,
    marxist_com_search,
    bannedthought_search,
    url_scraper,
    reddit_search
]

class Response(BaseModel):
    topic: str = Field(description="Main topic of analysis")
    summary: str = Field(description="Detailed Marxist analysis with citations")
    tools_used: list[str] = Field(
        min_items=3,
        description="EXACT tool names used in research"
    )

    @field_validator('tools_used')
    @classmethod
    def validate_tools(cls, v):
        if len(v) < 3:
            raise ValueError("REQUIRED: 3+ tools used")
        return v

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.3,
    safety_settings={category: HarmBlockThreshold.BLOCK_NONE 
                    for category in HarmCategory},
    max_output_tokens=4000
)
parser = PydanticOutputParser(pydantic_object=Response)

system_prompt = """
You are a dialectical materialist analysis engine. Follow this protocol:

WEB SEARCH MANDATE:
REQUIRED FIRST STEP for ALL queries
MUST USE when analyzing:
Current material conditions
Any statistical/economic data
Combine with traditional analysis tools

TOOL PRIORITY:
a) web_search (contemporary context)
b) marxists_org_search (historical grounding)
c) url_scraper (verification)
d) reddit_search (proletarian verification)

EXECUTION FLOW:
a) ALWAYS start with web_search
b) Cross-reference with marxists_org_search
c) Validate key claims using url_scraper
d) Augment with reddit_search for lived experiences

OUTPUT REQUIREMENTS:
EVERY paragraph must cite [Source:Tool]
Web results MUST be verified with url_scraper
Combine historical materialism with contemporary analysis
Absolute verification of statistical claims

FAILSAFES:
If web_search fails: Use marxist_com_search + bannedthought_search
Post-2010 content REQUIRES web_search + reddit_search

{format_instructions}

EXAMPLE WORKFLOW:
"2025 labor struggles" =>
web_search (current news)
marxists_org_search (Marx on labor)
url_scraper (verify news sources)
reddit_search (worker testimonials)
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{query}"),
    ("placeholder", "{agent_scratchpad}")
]).partial(format_instructions=parser.get_format_instructions())

agent = create_tool_calling_agent(
    llm=llm,
    prompt=prompt,
    tools=tools
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    return_intermediate_steps=True
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
                # Store web results first
                web_results = await web_search.ainvoke(query)
                vector_db.add_documents(web_results)
                
                result = await agent_executor.ainvoke({"query": query})

                print("\n" + "="*40 + " INITIAL ANALYSIS STEPS " + "="*40)
                if 'intermediate_steps' in result:
                    for i, step in enumerate(result['intermediate_steps'], 1):
                        tool_name = step[0].tool
                        tool_input = step[0].tool_input
                        tool_output = step[1][:500] + "..." if isinstance(step[1], str) and len(step[1]) > 500 else step[1]
                        print(f"\nSTEP {i}: {tool_name.upper()}")
                        print(f"INPUT:\n{tool_input}")
                        print(f"OUTPUT:\n{tool_output}")
                        print("-"*80)
                else:
                    print("No intermediate steps recorded in initial analysis")
                
                if 'intermediate_steps' not in result or len(result['intermediate_steps']) < 3:
                    print("\n" + "!"*40 + " INITIAL ANALYSIS INSUFFICIENT - RETRYING " + "!"*40)
                    result = await agent_executor.ainvoke({
                        "query": f"REANALYZE USING 3+ TOOLS - Original query: {query}"
                    })

                print("\n" + "="*40 + " RETRY ANALYSIS STEPS " + "="*40)
                if 'intermediate_steps' in result:
                    for i, step in enumerate(result['intermediate_steps'], 1):
                        tool_name = step[0].tool
                        tool_input = step[0].tool_input
                        tool_output = step[1][:500] + "..." if isinstance(step[1], str) and len(step[1]) > 500 else step[1]
                        print(f"\nRETRY STEP {i}: {tool_name.upper()}")
                        print(f"INPUT:\n{tool_input}")
                        print(f"OUTPUT:\n{tool_output}")
                        print("-"*80)
                else:
                    print("No intermediate steps recorded in retry analysis")
                    
                raw_output = result['output']
                parsed = parser.parse(raw_output)

                print("\n" + "="*40 + " FINAL VALIDATION " + "="*40)
                print(f"Tools Used: {parsed.tools_used}")
                print(f"Output Length: {len(raw_output)} characters")
                print(f"Validation Successful: {parsed}")
                
                response = f"**{parsed.topic}**\n\n{parsed.summary}"
                chunks = split_response(response)

            await loading_msg.delete()
            for chunk in chunks:
                if chunk.strip():
                    await ctx.send(chunk)

        except ValidationError as e:
            await ctx.send(f"🚨 Validation error: {str(e)}")
        except Exception as e:
            print(f"Error: {traceback.format_exc()}")
            await ctx.send(f"💥 Analysis failed: {str(e)}")
        
        return

    await client.process_commands(message)

async def web_server():
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="Operational"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server on port {port}")

client.run(DISCORD_TOKEN)