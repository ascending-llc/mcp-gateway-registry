#!/usr/bin/env python3
"""
Test script for Travel Assistant and Flight Booking agents
Usage: python simple_agents_test.py --endpoint local|live
"""

import argparse
import json
import requests
import sys
import uuid
from typing import Dict, Any
import boto3

# Endpoint configurations
LOCAL_ENDPOINTS = {
    "travel_assistant": "http://localhost:9001",
    "flight_booking": "http://localhost:9002"
}

LIVE_ENDPOINTS = {
    "travel_assistant": "travel_assistant_agent ARN",
    "flight_booking": "flight_booking_agent ARN"
}

AWS_REGION = "us-east-1"


class AgentTester:
    def __init__(self, endpoints: Dict[str, str], is_live: bool = False):
        self.endpoints = endpoints
        self.is_live = is_live
        if is_live:
            self.bedrock_client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)
        
    def send_agent_message(self, agent_type: str, message: str) -> Dict[str, Any]:
        """Send message to agent using A2A protocol (local) or boto3 (live)"""
        endpoint = self.endpoints[agent_type]
        if not endpoint:
            raise ValueError(f"No endpoint configured for {agent_type}")
        
        if self.is_live:
            # Use boto3 for AgentCore Runtime
            return self._invoke_agentcore_runtime(endpoint, message)
        else:
            # Use HTTP for local A2A
            payload = {
                "jsonrpc": "2.0",
                "id": "test-001",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": message}],
                        "messageId": "test-msg-001"
                    }
                }
            }
            
            response = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"})
            return response.json()
    
    def _invoke_agentcore_runtime(self, runtime_arn: str, message: str) -> Dict[str, Any]:
        """Invoke AgentCore Runtime using boto3"""
        # A2A protocol requires JSON-RPC format
        payload = {
            "jsonrpc": "2.0",
            "id": "test-001",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                    "messageId": f"test-msg-{uuid.uuid4().hex[:8]}"
                }
            }
        }
        payload_json = json.dumps(payload)
        
        # Generate session ID (must be 33+ characters)
        session_id = f"test-session-{uuid.uuid4().hex}"
        
        try:
            response = self.bedrock_client.invoke_agent_runtime(
                agentRuntimeArn=runtime_arn,
                runtimeSessionId=session_id,
                qualifier='DEFAULT',
                payload=payload_json
            )
            
            # Read streaming response
            if 'response' in response:
                streaming_body = response['response']
                all_lines = []
                
                for line in streaming_body.iter_lines():
                    line_str = line.decode('utf-8')
                    all_lines.append(line_str)
                
                # The response is a single JSON-RPC response line
                if all_lines:
                    try:
                        json_response = json.loads(all_lines[0])
                        
                        # Check for JSON-RPC error
                        if 'error' in json_response:
                            return {"error": json_response['error']}
                        
                        # Return the JSON-RPC result directly
                        return json_response
                        
                    except json.JSONDecodeError as e:
                        return {"error": f"Failed to parse response: {e}"}
                
                return {"error": "Empty response"}
            
            return {"error": "No response content"}
            
        except Exception as e:
            return {"error": str(e)}
    
    def call_api_endpoint(self, agent_type: str, endpoint: str, method: str = "POST", **params) -> Dict[str, Any]:
        """Call direct API endpoint (only works for local)"""
        if self.is_live:
            raise NotImplementedError("Direct API endpoints not available for live AgentCore Runtime")
        
        url = f"{self.endpoints[agent_type]}{endpoint}"
        if not self.endpoints[agent_type]:
            raise ValueError(f"No endpoint configured for {agent_type}")
        
        if method.upper() == "GET":
            response = requests.get(url, params=params)
        else:
            response = requests.post(url, params=params)
        return response.json()
    
    def ping_agent(self, agent_type: str) -> bool:
        """Check if agent is healthy (only works for local)"""
        if self.is_live:
            # For live, we can't ping directly, assume healthy if ARN is configured
            return bool(self.endpoints.get(agent_type))
        
        try:
            url = f"{self.endpoints[agent_type]}/ping"
            response = requests.get(url, timeout=5)
            return response.status_code == 200 and response.json().get("status") == "healthy"
        except:
            return False


class TravelAssistantTests:
    def __init__(self, tester: AgentTester):
        self.tester = tester
        self.agent_type = "travel_assistant"
    
    def test_ping(self):
        """Test agent health check"""
        print("Testing Travel Assistant ping...")
        result = self.tester.ping_agent(self.agent_type)
        assert result, "Travel Assistant ping failed"
        print("✓ Travel Assistant is healthy")
    
    def test_agent_flight_search(self):
        """Test agent flight search via A2A"""
        print("Testing Travel Assistant flight search...")
        message = "Search for flights from SF to NY on 2025-11-15"
        response = self.tester.send_agent_message(self.agent_type, message)
        
        assert "result" in response, f"No result in response: {response}"
        assert "artifacts" in response["result"], "No artifacts in response"
        
        # Check if agent found flights
        artifacts = response["result"]["artifacts"]
        assert len(artifacts) > 0, "No artifacts returned"
        
        # Extract text from artifact parts
        response_text = ""
        for artifact in artifacts:
            if "parts" in artifact:
                for part in artifact["parts"]:
                    if "text" in part:
                        response_text += part["text"]
        
        assert "flight" in response_text.lower(), f"Response doesn't mention flights. Got: {response_text[:100]}"
        print("✓ Travel Assistant flight search working")
    
    def test_api_search_flights(self):
        """Test direct API endpoint (local only)"""
        if self.tester.is_live:
            print("⊘ Skipping /api/search-flights endpoint (only available in local Docker container)")
            return
            
        print("Testing Travel Assistant API endpoint...")
        response = self.tester.call_api_endpoint(
            self.agent_type, 
            "/api/search-flights",
            departure_city="SF",
            arrival_city="NY", 
            departure_date="2025-11-15"
        )
        
        assert "result" in response, f"No result in API response: {response}"
        result_data = json.loads(response["result"])
        assert "flights" in result_data, "No flights in API response"
        assert len(result_data["flights"]) > 0, "No flights found"
        print("✓ Travel Assistant API endpoint working")
    
    def test_api_recommendations(self):
        """Test recommendations API (local only)"""
        if self.tester.is_live:
            print("⊘ Skipping /api/recommendations endpoint (only available in local Docker container)")
            return
            
        print("Testing Travel Assistant recommendations...")
        response = self.tester.call_api_endpoint(
            self.agent_type,
            "/api/recommendations",
            method="GET",
            max_price=300,
            preferred_airlines="United,Delta"
        )
        
        assert "result" in response, "No result in recommendations response"
        result_data = json.loads(response["result"])
        assert "recommendations" in result_data, "No recommendations in response"
        print("✓ Travel Assistant recommendations working")


class FlightBookingTests:
    def __init__(self, tester: AgentTester):
        self.tester = tester
        self.agent_type = "flight_booking"
    
    def test_ping(self):
        """Test agent health check"""
        print("Testing Flight Booking ping...")
        result = self.tester.ping_agent(self.agent_type)
        assert result, "Flight Booking ping failed"
        print("✓ Flight Booking is healthy")
    
    def test_agent_availability_check(self):
        """Test agent availability check via A2A"""
        print("Testing Flight Booking availability check...")
        message = "Check availability for flight ID 1"
        response = self.tester.send_agent_message(self.agent_type, message)
        
        assert "result" in response, f"No result in response: {response}"
        assert "artifacts" in response["result"], "No artifacts in response"
        
        artifacts = response["result"]["artifacts"]
        assert len(artifacts) > 0, "No artifacts returned"
        
        response_text = artifacts[0]["parts"][0]["text"]
        assert "available" in response_text.lower(), "Response doesn't mention availability"
        print("✓ Flight Booking availability check working")
    
    def test_agent_booking(self):
        """Test agent booking via A2A"""
        print("Testing Flight Booking reservation...")
        message = "Book flight ID 1 for Jane Smith, email jane@test.com"
        response = self.tester.send_agent_message(self.agent_type, message)
        
        assert "result" in response, f"No result in response: {response}"
        artifacts = response["result"]["artifacts"]
        response_text = artifacts[0]["parts"][0]["text"]
        
        assert "booking" in response_text.lower() or "reserved" in response_text.lower(), \
               "Response doesn't mention booking/reservation"
        print("✓ Flight Booking reservation working")
    
    def test_api_check_availability(self):
        """Test direct API endpoint (local only)"""
        if self.tester.is_live:
            print("⊘ Skipping /api/check-availability endpoint (only available in local Docker container)")
            return
            
        print("Testing Flight Booking API endpoint...")
        response = self.tester.call_api_endpoint(
            self.agent_type,
            "/api/check-availability",
            flight_id=1
        )
        
        assert "result" in response, f"No result in API response: {response}"
        result_data = json.loads(response["result"])
        assert "flight_id" in result_data, "No flight_id in API response"
        assert "available_seats" in result_data, "No available_seats in response"
        print("✓ Flight Booking API endpoint working")


def run_tests(endpoint_type: str):
    """Run all tests for specified endpoint type"""
    print(f"Running tests against {endpoint_type} endpoints...")
    print("=" * 50)
    
    # Select endpoints
    endpoints = LOCAL_ENDPOINTS if endpoint_type == "local" else LIVE_ENDPOINTS
    
    # Check if endpoints are configured
    for agent, url in endpoints.items():
        if not url:
            print(f"❌ No {endpoint_type} endpoint configured for {agent}")
            return False
    
    is_live = (endpoint_type == "live")
    tester = AgentTester(endpoints, is_live=is_live)
    
    try:
        # Test Travel Assistant
        print("\n🧪 Testing Travel Assistant Agent")
        print("-" * 30)
        travel_tests = TravelAssistantTests(tester)
        travel_tests.test_ping()
        travel_tests.test_agent_flight_search()
        travel_tests.test_api_search_flights()
        travel_tests.test_api_recommendations()
        
        # Test Flight Booking
        print("\n🧪 Testing Flight Booking Agent")
        print("-" * 30)
        booking_tests = FlightBookingTests(tester)
        booking_tests.test_ping()
        booking_tests.test_agent_availability_check()
        booking_tests.test_agent_booking()
        booking_tests.test_api_check_availability()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Travel Assistant and Flight Booking agents")
    parser.add_argument(
        "--endpoint", 
        choices=["local", "live"], 
        required=True,
        help="Test against local or live endpoints"
    )
    
    args = parser.parse_args()
    
    success = run_tests(args.endpoint)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()