import subprocess
import sys
from packaging import version
from collections import defaultdict

def get_available_versions(package_name):
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

def analyze_langchain_dependencies():
    print("\nAnalyzing LangChain package dependencies...")
    
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
        versions = get_available_versions(package)
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

if __name__ == "__main__":
    analyze_langchain_dependencies()