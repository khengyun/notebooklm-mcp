#!/usr/bin/env python3
"""
GitHub Copilot Integration Example
Demonstrates how to use NotebookLM MCP Server with GitHub Copilot
"""

import asyncio
import os
from typing import Dict, Any
from notebooklm_mcp import NotebookLMClient, ServerConfig


class CopilotNotebookLMIntegration:
    """Integration class for GitHub Copilot and NotebookLM MCP Server"""
    
    def __init__(self, notebook_id: str):
        self.config = ServerConfig(
            default_notebook_id=notebook_id,
            headless=True,
            debug=False
        )
        self.client = NotebookLMClient(self.config)
    
    async def analyze_code_with_notebook(self, code: str, context: str = "") -> str:
        """
        Analyze code using NotebookLM insights
        This method can be called by GitHub Copilot through MCP
        """
        try:
            await self.client.start()
            await self.client.authenticate()
            
            prompt = f"""
            Phân tích đoạn code sau dựa trên knowledge base trong notebook:
            
            Context: {context}
            
            Code:
            ```
            {code}
            ```
            
            Hãy đưa ra:
            1. Đánh giá chất lượng code
            2. Gợi ý cải thiện
            3. Best practices liên quan
            4. Potential issues
            """
            
            await self.client.send_message(prompt)
            response = await self.client.get_response(wait_for_completion=True)
            
            return response
            
        except Exception as e:
            return f"Error analyzing code: {str(e)}"
        finally:
            await self.client.close()
    
    async def get_research_insights(self, topic: str) -> str:
        """
        Get research insights from notebook for a specific topic
        """
        try:
            await self.client.start()
            await self.client.authenticate()
            
            prompt = f"""
            Dựa trên tài liệu trong notebook, hãy cung cấp insights về: {topic}
            
            Include:
            - Key findings
            - Relevant examples
            - Best practices
            - Implementation recommendations
            """
            
            await self.client.send_message(prompt)
            response = await self.client.get_response(wait_for_completion=True)
            
            return response
            
        except Exception as e:
            return f"Error getting insights: {str(e)}"
        finally:
            await self.client.close()
    
    async def generate_documentation(self, code: str, style_guide: str = "") -> str:
        """
        Generate documentation for code using notebook style guidelines
        """
        try:
            await self.client.start()
            await self.client.authenticate()
            
            prompt = f"""
            Tạo documentation cho code sau theo style guide trong notebook:
            
            Style Guide Context: {style_guide}
            
            Code:
            ```
            {code}
            ```
            
            Generate:
            - Function/class descriptions
            - Parameter documentation
            - Return value descriptions
            - Usage examples
            - Notes about implementation
            """
            
            await self.client.send_message(prompt)
            response = await self.client.get_response(wait_for_completion=True)
            
            return response
            
        except Exception as e:
            return f"Error generating documentation: {str(e)}"
        finally:
            await self.client.close()


# Example usage for GitHub Copilot
async def main():
    """Example usage that GitHub Copilot can reference"""
    
    # Replace with your actual notebook ID
    notebook_id = os.getenv("NOTEBOOKLM_NOTEBOOK_ID", "your-notebook-id")
    integration = CopilotNotebookLMIntegration(notebook_id)
    
    # Example 1: Analyze code
    sample_code = """
    def process_data(data):
        result = []
        for item in data:
            if item > 0:
                result.append(item * 2)
        return result
    """
    
    analysis = await integration.analyze_code_with_notebook(
        sample_code, 
        "Python data processing function"
    )
    print("Code Analysis:", analysis)
    
    # Example 2: Get research insights
    insights = await integration.get_research_insights("machine learning best practices")
    print("Research Insights:", insights)
    
    # Example 3: Generate documentation
    docs = await integration.generate_documentation(sample_code)
    print("Generated Documentation:", docs)


if __name__ == "__main__":
    asyncio.run(main())