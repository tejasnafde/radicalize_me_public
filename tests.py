#!/usr/bin/env python3
"""
Comprehensive test suite for the Marxist Analysis Discord Bot
Contains all testing functions for different components of the system.
"""

import os
import sys
import asyncio
import argparse
import subprocess
from packaging import version
from collections import defaultdict
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from helpers.research_pipeline import ResearchPipeline
from handlers.bot_handler import BotHandler


class BotTestSuite:
    """Comprehensive test suite for the bot system"""
    
    def __init__(self):
        self.results = {}
    
    async def test_llm_providers(self):
        """Test individual LLM providers to check availability"""
        print("=== Testing LLM Providers ===")
        
        # Test Groq
        groq_result = await self._test_groq()
        
        # Test Gemini  
        gemini_result = await self._test_gemini()
        
        self.results['llm_providers'] = {
            'groq': groq_result,
            'gemini': gemini_result
        }
        
        print(f"\n=== LLM Provider Results ===")
        print(f"Groq: {'✓' if groq_result else '✗'}")
        print(f"Gemini: {'✓' if gemini_result else '✗'}")
        
        return groq_result or gemini_result
    
    async def _test_groq(self):
        """Test Groq provider"""
        try:
            print("Testing Groq...")
            groq = ChatGroq(
                model_name="llama3-70b-8192",
                temperature=0.3,
                max_tokens=100,
                groq_api_key=os.getenv('GROQ_API_KEY'),
                max_retries=0,
                timeout=10
            )
            
            response = await groq.ainvoke([HumanMessage(content="Test message: respond with 'Groq working'")])
            print(f"Groq SUCCESS: {response.content}")
            return True
        except Exception as e:
            print(f"Groq FAILED: {e}")
            return False

    async def _test_gemini(self):
        """Test Gemini provider"""
        try:
            print("Testing Gemini...")
            import google.generativeai as genai
            genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
            
            gemini = ChatGoogleGenerativeAI(
                model="gemini-1.5-pro",
                temperature=0.3,
                convert_system_message_to_human=True,
                max_output_tokens=100,
                max_retries=0,
                timeout=15
            )
            
            response = await gemini.ainvoke([HumanMessage(content="Test message: respond with 'Gemini working'")])
            print(f"Gemini SUCCESS: {response.content}")
            return True
        except Exception as e:
            print(f"Gemini FAILED: {e}")
            return False

    async def test_pipeline(self):
        """Test the complete research pipeline"""
        print("\n=== Testing Research Pipeline ===")
        
        try:
            pipeline = ResearchPipeline()
            result = await pipeline.process_query('tell me about mao and stalins relationship')
            
            self.results['pipeline'] = {
                'success': True,
                'topic': result.topic,
                'has_sources': len(getattr(result, 'sources_used', [])) > 0,
                'has_citations': '[Source' in result.summary
            }
            
            print('Pipeline SUCCESS!')
            print(f'Topic: {result.topic}')
            print(f'Summary (first 200 chars): {result.summary[:200]}...')
            print(f'Tools: {result.tools_used}')
            print(f'Sources found: {len(getattr(result, "sources_used", []))}')
            return True
            
        except Exception as e:
            print(f'Pipeline FAILED: {e}')
            self.results['pipeline'] = {'success': False, 'error': str(e)}
            return False

    async def test_bot_handler(self):
        """Test the bot handler with source display"""
        print("\n=== Testing Bot Handler ===")
        
        try:
            bot_handler = BotHandler()
            result = await bot_handler.handle_request('what is historical materialism?', '123', '456')
            
            if "message" in result:
                content = result["message"].get("content", "")
                has_sources = "**Sources:**" in content
                has_methods = "**Analysis Methods:**" in content
                
                self.results['bot_handler'] = {
                    'success': True,
                    'displays_sources': has_sources,
                    'displays_methods': has_methods,
                    'content_length': len(content)
                }
                
                print('Bot Handler SUCCESS!')
                print(f'Sources displayed: {"✓" if has_sources else "✗"}')
                print(f'Methods displayed: {"✓" if has_methods else "✗"}')
                return True
            else:
                raise Exception("No message in result")
                
        except Exception as e:
            print(f'Bot Handler FAILED: {e}')
            self.results['bot_handler'] = {'success': False, 'error': str(e)}
            return False

    async def test_source_display(self):
        """Test specifically that sources are displayed correctly"""
        print("\n=== Testing Source Display Fix ===")
        
        try:
            bot_handler = BotHandler()
            result = await bot_handler.handle_request('explain democratic centralism', '123', '456')
            
            if "message" in result:
                content = result["message"].get("content", "")
                
                # Check various display elements
                has_sources_section = "**Sources:**" in content
                has_clickable_links = "](http" in content
                has_checkmarks = " ✓" in content
                has_analysis_methods = "**Analysis Methods:**" in content
                
                self.results['source_display'] = {
                    'success': True,
                    'sources_section': has_sources_section,
                    'clickable_links': has_clickable_links,
                    'checkmarks': has_checkmarks,
                    'analysis_methods': has_analysis_methods
                }
                
                print('Source Display Test SUCCESS!')
                print(f'Sources section: {"✓" if has_sources_section else "✗"}')
                print(f'Clickable links: {"✓" if has_clickable_links else "✗"}')
                print(f'Checkmarks for cited: {"✓" if has_checkmarks else "✗"}')
                print(f'Analysis methods: {"✓" if has_analysis_methods else "✗"}')
                
                if has_sources_section:
                    print("✅ FIXED: Sources are being displayed correctly!")
                else:
                    print("❌ BROKEN: Only showing analysis methods")
                
                return has_sources_section
            else:
                raise Exception("No message in result")
                
        except Exception as e:
            print(f'Source Display Test FAILED: {e}')
            self.results['source_display'] = {'success': False, 'error': str(e)}
            return False

    async def test_queue_system(self):
        """Test the queue system functionality"""
        print("\n=== Testing Queue System ===")
        
        try:
            # Import queue system components
            from helpers.queue_manager import QueueManager
            from helpers.discord_notifier import DiscordNotifier
            
            queue_manager = QueueManager()
            
            # Test basic queue operations
            query_id = queue_manager.add_query("test queue query", "test_user_123")
            position = queue_manager.get_position(query_id)
            queue_manager.complete_query(query_id)
            
            self.results['queue_system'] = {
                'success': True,
                'can_add_query': query_id is not None,
                'can_get_position': position is not None,
                'can_complete': True
            }
            
            print('Queue System SUCCESS!')
            print(f'Query ID generated: {query_id}')
            print(f'Position tracked: {position}')
            return True
            
        except Exception as e:
            print(f'Queue System FAILED: {e}')
            self.results['queue_system'] = {'success': False, 'error': str(e)}
            return False

    def get_available_versions(self, package_name):
        """Get available versions for a Python package"""
        try:
            print(f"Checking versions for {package_name}...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "index", "versions", package_name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                versions = []
                for line in result.stdout.split('\n'):
                    if 'Available versions:' in line:
                        versions = line.split(':')[1].strip().split(', ')
                print(f"Found versions for {package_name}: {versions}")
                return versions
            print(f"No versions found for {package_name}")
            return []
        except Exception as e:
            print(f"Error checking versions for {package_name}: {str(e)}")
            return []

    def analyze_requirements(self):
        """Analyze LangChain package dependencies and find compatible versions"""
        print("\n=== Analyzing LangChain Dependencies ===")
        
        # Core packages to analyze
        packages = {
            'langchain': None,
            'langchain-community': None,
            'langchain-core': None,
            'langchain-google-genai': None,
            'langchain-huggingface': None,
            'langchain-groq': None,
            'langchain-text-splitters': None
        }
        
        # Get available versions for each package
        for package in packages:
            versions = self.get_available_versions(package)
            if versions:
                packages[package] = versions
                print(f"\n{package} versions:")
                for v in versions[:5]:  # Show first 5 versions
                    print(f"  - {v}")
        
        # Analyze core dependencies
        print("\nAnalyzing core dependencies...")
        core_versions = packages['langchain-core']
        if core_versions:
            print("\nLangChain Core version requirements:")
            print("-----------------------------------")
            for package, versions in packages.items():
                if package != 'langchain-core' and versions:
                    print(f"\n{package}:")
                    # Check each version's requirements
                    for v in versions[:3]:  # Check first 3 versions
                        try:
                            result = subprocess.run(
                                [sys.executable, "-m", "pip", "show", f"{package}=={v}"],
                                capture_output=True,
                                text=True
                            )
                            if result.returncode == 0:
                                for line in result.stdout.split('\n'):
                                    if 'Requires:' in line:
                                        print(f"  {v}: {line.split('Requires:')[1].strip()}")
                        except Exception as e:
                            print(f"  Error checking {v}: {str(e)}")
        
        # Find compatible version combinations
        print("\nSearching for compatible version combinations...")
        compatible_combinations = []
        
        # Start with older versions of langchain-core that might work with groq
        if core_versions:
            for core_version in core_versions:
                if version.parse(core_version) < version.parse('0.2.0'):
                    print(f"\nTrying langchain-core {core_version}...")
                    try:
                        # Create a test requirements file
                        test_reqs = [
                            f"langchain-core=={core_version}",
                            "langchain-groq==0.1.0"
                        ]
                        
                        with open('test_requirements.txt', 'w') as f:
                            f.write('\n'.join(test_reqs))
                        
                        # Try installing
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", "test_requirements.txt"],
                            capture_output=True,
                            text=True
                        )
                        
                        if result.returncode == 0:
                            print(f"Found compatible combination with langchain-core {core_version}")
                            compatible_combinations.append({
                                'langchain-core': core_version,
                                'langchain-groq': '0.1.0'
                            })
                    except Exception as e:
                        print(f"Error testing combination: {str(e)}")
        
        if compatible_combinations:
            print("\nCompatible version combinations found:")
            print("-----------------------------------")
            for combo in compatible_combinations:
                print(f"\nCombination {combo}")
                print("To use this combination, update requirements.txt with:")
                print(f"langchain-core=={combo['langchain-core']}")
                print("langchain-groq==0.1.0")
        else:
            print("\nNo compatible combinations found that include Groq.")
            print("Consider using an alternative to Groq or updating the Groq package to support newer LangChain versions.")
        
        self.results['requirements_analysis'] = {
            'success': True,
            'packages_analyzed': len(packages),
            'compatible_combinations': len(compatible_combinations)
        }
        
        return len(compatible_combinations) > 0

    def print_summary(self):
        """Print a summary of all test results"""
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        total_tests = 0
        passed_tests = 0
        
        for test_name, result in self.results.items():
            total_tests += 1
            if result.get('success', False):
                passed_tests += 1
                status = "✓ PASS"
            else:
                status = "✗ FAIL"
            
            print(f"{test_name:<20} {status}")
            
            # Print additional details for failures
            if not result.get('success', False) and 'error' in result:
                print(f"{'':>22} Error: {result['error'][:100]}...")
        
        print("-" * 80)
        print(f"TOTAL: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 ALL TESTS PASSED!")
        else:
            print("⚠️  Some tests failed - check logs above")

    async def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting comprehensive bot test suite...")
        
        # Run all tests
        await self.test_llm_providers()
        await self.test_pipeline()
        await self.test_bot_handler()
        await self.test_source_display()
        await self.test_queue_system()
        
        # Print summary
        self.print_summary()
        
    async def run_requirements_analysis(self):
        """Run only requirements analysis"""
        print("🔍 Starting requirements analysis...")
        self.analyze_requirements()
        self.print_summary()


async def main():
    """Main function with CLI argument parsing"""
    parser = argparse.ArgumentParser(description="Marxist Bot Test Suite & Utilities")
    parser.add_argument("--test", choices=[
        "llm", "pipeline", "handler", "sources", "queue", "requirements", "all"
    ], default="all", help="Specific test to run")
    
    args = parser.parse_args()
    
    test_suite = BotTestSuite()
    
    if args.test == "llm":
        await test_suite.test_llm_providers()
    elif args.test == "pipeline":
        await test_suite.test_pipeline()
    elif args.test == "handler":
        await test_suite.test_bot_handler()
    elif args.test == "sources":
        await test_suite.test_source_display()
    elif args.test == "queue":
        await test_suite.test_queue_system()
    elif args.test == "requirements":
        await test_suite.run_requirements_analysis()
    else:  # "all"
        await test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main()) 