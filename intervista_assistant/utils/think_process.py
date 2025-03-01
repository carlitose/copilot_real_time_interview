#!/usr/bin/env python3
"""
Module for handling advanced thinking processes using OpenAI models.
"""

import logging
import json
from typing import List, Dict, Any
from openai import OpenAI

# Logging configuration
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

class ThinkProcess:
    """
    Class to handle the advanced thinking process using a two-step AI approach:
    1. Use GPT-4o-mini to summarize the conversation history
    2. Send the summary to o1-preview for deeper analysis and problem solving
    """
    
    def __init__(self, client: OpenAI):
        """
        Initialize the ThinkProcess with an OpenAI client.
        
        Args:
            client (OpenAI): The OpenAI client instance
        """
        self.client = client
    
    def summarize_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """
        Use GPT-4o-mini to summarize the conversation history.
        
        Args:
            messages: The conversation history
            
        Returns:
            str: A summary of the conversation
        """
        try:
            logger.info("Generating conversation summary with GPT-4o-mini")
            
            # Create a summary prompt
            summary_prompt = {
                "role": "system",
                "content": """Analyze the conversation history and create a concise summary in English. 
                Focus on:
                1. Key problems or questions discussed
                2. Important context
                3. Any programming challenges mentioned
                4. Current state of the discussion
                
                Your summary should be comprehensive but brief, highlighting the most important aspects 
                that would help another AI model solve any programming or logical problems mentioned."""
            }
            
            # Clone the messages and add the system prompt
            summary_messages = [summary_prompt] + messages
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=summary_messages
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return f"Error summarizing conversation: {e}"
    
    def deep_thinking(self, summary: str, problem_statement: str = None) -> str:
        """
        Use o1-preview to perform deep analysis and problem solving based on the conversation summary.
        
        Args:
            summary: The summary of the conversation
            problem_statement: Optional specific problem to focus on
            
        Returns:
            str: The solution or analysis from o1-preview
        """
        try:
            logger.info("Performing deep thinking with o1-preview")
            
            # Construct the prompt
            prompt = """
            I'm working on a programming or logical task. Here's the context and problem:
            
            # CONTEXT
            {}
            
            """.format(summary)
            
            # Add specific problem statement if provided
            if problem_statement:
                prompt += f"""
                # SPECIFIC PROBLEM TO SOLVE
                {problem_statement}
                """
            
            prompt += """
            Please analyze this situation and:
            1. Identify the core problem or challenge
            2. Develop a structured approach to solve it
            3. Provide a detailed solution with code if applicable
            4. Explain your reasoning
            """
            
            response = self.client.chat.completions.create(
                model="o1-preview",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error in deep thinking process: {e}")
            return f"Error in deep thinking process: {e}"
    
    def process(self, messages: List[Dict[str, Any]], problem_statement: str = None) -> Dict[str, str]:
        """
        Complete process: summarize with GPT-4o-mini and then analyze with o1-preview.
        
        Args:
            messages: The conversation history
            problem_statement: Optional specific problem to focus on
            
        Returns:
            Dict with summary and solution
        """
        try:
            # Step 1: Generate summary with GPT-4o-mini
            summary = self.summarize_conversation(messages)
            
            # Step 2: Deep thinking with o1-preview
            solution = self.deep_thinking(summary, problem_statement)
            
            return {
                "summary": summary,
                "solution": solution
            }
            
        except Exception as e:
            logger.error(f"Error in think process: {e}")
            return {
                "summary": f"Error generating summary: {e}",
                "solution": f"Error generating solution: {e}"
            } 