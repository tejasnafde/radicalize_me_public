from dotenv import load_dotenv
load_dotenv()

import discord
import re
import os
import json
import asyncio
from aiohttp import web
import traceback
from discord.ext import commands
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ValidationError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from google.generativeai.types.safety_types import HarmCategory, HarmBlockThreshold
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated


from tools import restricted_web_search, url_scraper, reddit_search, safe_ai_call
research_tools = [restricted_web_search, url_scraper]
analysis_tools = [url_scraper, reddit_search]

research_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a research assistant. Optimize search queries for Marxist research.
Output ONLY the optimized search query - maximum 100 characters. No explanations."""),
    ("human", "{query}")
])

research_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.2,
    safety_settings={category: HarmBlockThreshold.BLOCK_NONE 
                    for category in HarmCategory}
)

research_chain = research_prompt | research_llm | StrOutputParser()

KEEP_ALIVE_CHANNEL_ID = 881890878308896778
BOT_ID = None
PING_INTERVAL = 600

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

tools = [
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

# system_prompt = """
# You are a dialectical materialist analysis engine. Follow this protocol:

# 1. TOOL MANDATE:
#    - REQUIRED: Use EXACTLY 3 tools minimum
#    - Required Tools for ALL Queries:
#      a) marxists_org_search (historical context)
#      b) marxist_com_search OR bannedthought_search (modern analysis)
#      c) reddit_search (proletarian perspective)
#    - url_scraper MANDATORY when citing specific URLs

# 2. EXECUTION FLOW:
#    a) ALWAYS start with marxists_org_search
#    b) THEN modern analysis tool
#    c) THEN reddit_search
#    d) FINALLY url_scraper if sources cited

# 3. OUTPUT REQUIREMENTS:
#    - Each paragraph MUST contain [Source:ToolName] citations
#    - Tools used MUST match citations
#    - ABSOLUTELY NO unsourced claims
#    - Output must be as exhaustive as possible, keeping the length around 500-1000 words, but DO NOT lengthen the text if you cannot find sufficient relevant information.

# 4. FAILURE MODES:
#    - If ANY tool returns no results: STATE WHICH TOOL FAILED
#    - If <3 tools used: OUTPUT INVALID - RETRY ANALYSIS
#    - If post-2010 content: REQUIRE reddit_search + url_scraper

# {format_instructions}

# EXAMPLE WORKFLOW:
# 1. "US labor strikes" => 
#    - marxists_org_search (Marx on labor)
#    - marxist_com_search (modern strike analysis)
#    - reddit_search (worker experiences)
#    - url_scraper (verify marxist.com article)
# """

analysis_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a Marxist analyst. Use provided research context and tools.
        
    RESEARCH CONTEXT:
    {context}

    ANALYSIS PROTOCOL:
    1. Cross-reference sources
    2. Apply historical materialism
    3. Cite sources with [Source#] notation
    4. Use the agent scratchpad for intermediate steps: {agent_scratchpad}"""),
    ("human", "{query}")
])

analysis_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    temperature=0.3,
    safety_settings={category: HarmBlockThreshold.BLOCK_NONE 
                    for category in HarmCategory},
    max_output_tokens=4000
)

print(f"Type of analysis_prompt: {type(analysis_prompt)}")
print(f"Type of analysis_tools: {type(analysis_tools)}")

analysis_agent = create_tool_calling_agent(analysis_llm, analysis_tools, analysis_prompt)
agent_executor = AgentExecutor(agent=analysis_agent, tools=analysis_tools, verbose=True)
# prompt = ChatPromptTemplate.from_messages([
#     ("system", system_prompt),
#     ("human", "{query}"),
#     ("placeholder", "{agent_scratchpad}")
# ]).partial(format_instructions=parser.get_format_instructions())

# agent = create_tool_calling_agent(
#     llm=llm,
#     prompt=prompt,
#     tools=tools
# )

# agent_executor = AgentExecutor(
#     agent=agent,
#     tools=tools,
#     verbose=True,
#     return_intermediate_steps=True
# )

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
        # Modified research phase in on_message()
        try:
            loading_msg = await ctx.send("⚙️ Processing query...")
            
            # Get optimized query
            research_response = await research_chain.ainvoke({"query": query})
            print(f"19apr debug {research_response=}")
            # Execute web search with optimized query
            try:
                search_results = await restricted_web_search.ainvoke({"query": research_response})
                if 'content' in search_results and search_results['content'].startswith("Search error:"):
                    search_results = await restricted_web_search.ainvoke({"query": query + " site:marxists.org"})
            except Exception as e:
                print(f"Search error: {str(e)}")

            print(f"Search results: {search_results}")
            
            if 'content' in search_results and search_results['content']:
                print(f"19apr debug search_results['content']={search_results['content']}")
                
                # Check if the content indicates an error
                if search_results['content'].startswith("Search error:"):
                    await ctx.send("⚠️ Search error occurred. Please try again later.")
                    return
                
                try:
                    search_data = json.loads(search_results['content'])
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {str(e)}")
                    await ctx.send("⚠️ Error processing search results: Invalid JSON format.")
                    return
            else:
                print("No content found in search results.")
                await ctx.send("⚠️ No search results returned.")
                return
            
            # Scrape and process results
            context = {
                "original_query": query,
                "optimized_query": research_response,
                "sources": []
            }
            print(f"19apr debug {context=}")
            # Process search results and scrape content
            for item in search_data[:3]:  # Limit to 3 sources for depth
                if 'url' in item:
                    try:
                        scraped = await url_scraper.ainvoke({"url": item["url"]})
                        context["sources"].append({
                            "url": item["url"],
                            "content": scraped['content'][:2000]
                        })
                    except Exception as e:
                        print(f"Error scraping {item['url']}: {str(e)}")
                        continue

            # Add Reddit perspectives
            reddit_results = await reddit_search.ainvoke({"query": query})
            if reddit_results['content'] != "No relevant Reddit discussions found":
                context["sources"].append({
                    "type": "reddit",
                    "content": reddit_results['content'],
                    "urls": reddit_results['sources']
                })
            # Step 4: Run analysis with the formatted context
            await loading_msg.edit(content="📊 Performing dialectical analysis...")
            
            analysis_response = await agent_executor.ainvoke({
                "query": query,
                "context": json.dumps(context),
                "agent_scratchpad": [],
                "format_instructions": parser.get_format_instructions()  # Add format instructions
            })

            try:
                validated = parser.parse(analysis_response['output'])
                output = f"## {validated.topic}\n\n{validated.summary}"
                output += f"\n\n*Tools used: {', '.join(validated.tools_used)}*"
            except ValidationError:
                output = analysis_response['output']
            
            # Step 5: Send the response in chunks
            await loading_msg.delete()
            chunks = split_response(output)
            
            if not chunks:
                await ctx.send("⚠️ No analysis could be generated")
                return
                
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await ctx.send(f"**Analysis of '{query[:50]}...'**\n\n{chunk}")
                else:
                    await ctx.send(chunk)
        except ValidationError as e:
            await ctx.send(f"🚨 Validation error: {str(e)}")
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Analysis timed out - please try a more specific query")
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