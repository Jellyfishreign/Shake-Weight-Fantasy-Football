#!/usr/bin/env python3
"""
The Quantum Gauntlet - Playoff Dashboard
Startup script for the real-time visualization application
"""

import sys
import os
import subprocess
import time

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = [
        'flask',
        'flask_socketio', 
        'requests',
        'gspread',
        'pytz'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n📦 Install dependencies with:")
        print("   pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies are installed")
    return True

def main():
    print("🏈 The Quantum Gauntlet - Playoff Dashboard")
    print("=" * 50)
    
    # Check if app.py exists
    if not os.path.exists('app.py'):
        print("❌ Error: app.py not found in current directory")
        print("   Make sure you're running this script from the project directory")
        return
    
    # Check dependencies
    if not check_dependencies():
        return
    
    print("\n🚀 Starting the application...")
    print("   The dashboard will be available at: http://localhost:5000")
    print("   Press Ctrl+C to stop the application")
    print("\n" + "=" * 50)
    
    try:
        # Import and run the Flask app
        from app import app, socketio
        
        print("✅ Application started successfully!")
        print("🌐 Open your browser and go to: http://localhost:5000")
        print("📊 Real-time playoff data will update automatically")
        
        # Run the application
        socketio.run(app, debug=True, host='0.0.0.0', port=5000)
        
    except KeyboardInterrupt:
        print("\n\n👋 Application stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting application: {e}")
        print("   Check that all files are in the correct location")
        print("   Verify your Sleeper API credentials in app.py")

if __name__ == "__main__":
    main() 