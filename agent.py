import json
from openai import OpenAI
from dotenv import load_dotenv

from tools.student_tools import (
    get_student_profile,
    create_support_request
)
from memory.store import get_memories, save_memory
from retrieval.policy import retrieve_policy


load_dotenv()
client = OpenAI()


# Tools available to UniPilot
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_student_profile",
            "description": "Get the logged-in student's own profile.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_academic_info",
            "description": (
                "Search both available student knowledge-base PDFs: the academic "
                "plan and the AIDTM UniPilot Student Handbook draft. Use this for "
                "academic schedules, subjects, trimester information, attendance, "
                "examinations, student support, SIP, Industrial Capstone and "
                "placement-policy questions. The result includes source, page and "
                "status metadata; preserve these distinctions in your answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The student's academic or institute-policy question."
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_memories",
            "description": "Recall useful information saved for the logged-in student.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_student_memory",
            "description": "Save useful non-sensitive information for future conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_request",
            "description": (
                "Prepare a student support request. This action requires explicit "
                "student confirmation before the request is actually created."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["subject", "description"]
            }
        }
    }
]


def execute_tool(name, arguments, student_id):
    """Execute tools using the authenticated student's ID."""

    if name == "get_student_profile":
        return get_student_profile(student_id)

    if name == "retrieve_academic_info":
        return retrieve_policy(arguments["question"])

    if name == "get_student_memories":
        return get_memories(student_id)

    if name == "save_student_memory":
        return save_memory(
            student_id,
            arguments["key"],
            arguments["value"]
        )

    if name == "create_support_request":
        # Prepare only. The request is not created until explicit confirmation
        # is implemented and received through the application.
        return {
            "success": True,
            "approval_required": True,
            "pending_request": {
                "subject": arguments["subject"],
                "description": arguments["description"]
            },
            "message": (
                "This support request is only prepared, not submitted. "
                "Ask the student for explicit confirmation before execution."
            )
        }

    return {
        "success": False,
        "message": "Unknown tool."
    }


def run_agent(question, student_id, history=None):
    """Run the UniPilot agent and its tool-calling loop."""

    if not student_id:
        return {
            "success": False,
            "response": "Please log in to use UniPilot.",
            "tools_used": []
        }

    system_prompt = """
You are UniPilot, an AI-powered student support assistant for the AIDTM
student-support project. The configured language model is OpenAI GPT-4o-mini.
If asked which assistant/model you are, identify yourself as UniPilot and
state that it is powered by OpenAI GPT-4o-mini.

Knowledge and source rules:
1. For questions about academic schedules, subjects, institute policies,
   attendance, examinations, SIP, Industrial Capstone or placements, use
   retrieve_academic_info before answering.
2. The retrieval tool searches both the academic plan and the AIDTM UniPilot
   Student Handbook draft. Read the returned source, page and status metadata.
3. Clearly distinguish:
   - SOURCE DOCUMENT: information extracted from an available source document.
   - SOURCE-BASED SUMMARY: a summary in the handbook based on the named
     AIDTM SIP/Industrial Capstone/Placement policy document.
   - ILLUSTRATIVE SAMPLE — NOT AN OFFICIAL AIDTM RULE: demonstration content
     that must never be presented as an actual AIDTM policy.
   - DRAFT HANDBOOK: the handbook as a whole is a demonstration draft; this
     label does not automatically make every section illustrative.
4. Never describe a source-based placement-policy summary as an illustrative
   sample merely because it appears inside the draft handbook.
5. Never invent attendance percentages, deadlines, penalties, dates, fees,
   academic rules, student records or policy details.
6. If a question asks for a rule that is not established by the retrieved
   source, say that the available documents do not confirm it and recommend
   checking the latest official AIDTM communication.
7. Mention the source document and page number when retrieval provides them.
8. Do not claim the demonstration handbook is an official AIDTM-issued
   handbook. Be transparent that it is a project knowledge-base draft.

Student data and actions:
- Use tools when student-specific information is needed.
- Use only the authenticated student's data. Never invent student records.
- The authenticated student ID is supplied by the application; never ask the
  model or user to substitute another student's ID.
- Do not store passwords, OTPs, PINs, financial credentials or other sensitive
  information in memory.
- A support request returned with approval_required=true is only prepared.
  It has NOT been submitted or created. Do not claim it was created.
- Answer clearly, simply and concisely. If the documents do not contain an
  answer, say so rather than guessing.
"""

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        # Keep only ordinary chat messages; do not pass prior tool-call objects
        # or system messages from the UI into a new agent run.
        for item in history[-8:]:
            if (
                isinstance(item, dict)
                and item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str)
            ):
                messages.append({
                    "role": item["role"],
                    "content": item["content"]
                })

    messages.append({
        "role": "user",
        "content": question
    })

    tools_used = []

    try:
        for _ in range(5):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2
            )

            message = response.choices[0].message

            # Convert the SDK message to a plain dictionary for the next
            # request's message history.
            assistant_message = {
                "role": "assistant",
                "content": message.content or ""
            }

            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments
                        }
                    }
                    for call in message.tool_calls
                ]

            messages.append(assistant_message)

            if not message.tool_calls:
                return {
                    "success": True,
                    "response": message.content or "",
                    "tools_used": tools_used
                }

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(
                    tool_call.function.arguments or "{}"
                )

                tools_used.append(tool_name)

                result = execute_tool(
                    tool_name,
                    arguments,
                    student_id
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str)
                })

        return {
            "success": False,
            "response": "I could not complete the request. Please try again.",
            "tools_used": tools_used
        }

    except Exception as error:
        return {
            "success": False,
            "response": f"Agent error: {str(error)}",
            "tools_used": tools_used
        }
