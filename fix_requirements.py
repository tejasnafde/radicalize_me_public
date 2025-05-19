import subprocess
import sys
from packaging import version
from collections import defaultdict

def get_available_versions(package_name):
    try:
        print(f"Checking versions for {package_name}...")  # Debug print
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
            print(f"Found versions for {package_name}: {versions}")  # Debug print
            return versions
        print(f"No versions found for {package_name}")  # Debug print
        return []
    except Exception as e:
        print(f"Error checking versions for {package_name}: {str(e)}")  # Debug print
        return []

def fix_requirements():
    print("Starting requirements check...")  # Debug print
    try:
        with open('requirements.txt', 'r') as f:
            requirements = f.readlines()
        print(f"Found {len(requirements)} requirements in requirements.txt")  # Debug print
    except Exception as e:
        print(f"Error reading requirements.txt: {str(e)}")
        return

    fixed_requirements = []
    issues = defaultdict(list)

    for req in requirements:
        req = req.strip()
        if not req:
            continue

        print(f"\nProcessing requirement: {req}")  # Debug print
        try:
            package_name = req.split('==')[0]
            current_version = req.split('==')[1] if '==' in req else None
            print(f"Package: {package_name}, Current version: {current_version}")  # Debug print

            if current_version:
                available_versions = get_available_versions(package_name)
                if available_versions:
                    latest_version = available_versions[0]
                    print(f"Latest version available: {latest_version}")  # Debug print
                    if version.parse(current_version) > version.parse(latest_version):
                        fixed_req = f"{package_name}=={latest_version}"
                        issues['version_mismatch'].append({
                            'package': package_name,
                            'current': current_version,
                            'latest': latest_version
                        })
                        fixed_requirements.append(fixed_req)
                        continue
                else:
                    issues['no_versions'].append({
                        'package': package_name,
                        'current': current_version
                    })

            fixed_requirements.append(req)
        except Exception as e:
            print(f"Error processing {req}: {str(e)}")  # Debug print
            issues['error'].append({
                'package': package_name if 'package_name' in locals() else req,
                'error': str(e)
            })
            fixed_requirements.append(req)

    # Write fixed requirements
    print("\nWriting fixed requirements to requirements.txt...")  # Debug print
    with open('requirements.txt', 'w') as f:
        f.write('\n'.join(fixed_requirements))

    # Print detailed report
    print("\nRequirements Analysis Report")
    print("==========================")
    
    if issues['version_mismatch']:
        print("\nVersion Mismatches (Current > Latest):")
        print("-------------------------------------")
        for issue in issues['version_mismatch']:
            print(f"- {issue['package']}: {issue['current']} → {issue['latest']}")
    
    if issues['no_versions']:
        print("\nPackages with No Available Versions:")
        print("----------------------------------")
        for issue in issues['no_versions']:
            print(f"- {issue['package']} (current: {issue['current']})")
    
    if issues['error']:
        print("\nErrors Processing Packages:")
        print("-------------------------")
        for issue in issues['error']:
            print(f"- {issue['package']}: {issue['error']}")
    
    if not any(issues.values()):
        print("\nNo issues found! All requirements are up to date.")

if __name__ == "__main__":
    fix_requirements()