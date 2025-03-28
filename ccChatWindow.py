import sys
import os
import json
import datetime
import re

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QCoreApplication
from PyQt5.QtGui import QTextOption
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QStyle,QMessageBox
from PyQt5.QtWidgets import QLabel, QListWidgetItem

from pathlib import Path
from openai import OpenAI

TITLE="CloudCompare LLM AI Integration Demo (by Zhouxin Xi)"
OPENAI_API_KEY = YOUR_OPEN_ROUTER_API_KEY
OPENAI_API_BASE="https://openrouter.ai/api/v1"
LOCAL_API_DOCS="cloudcompare_api.json"



MODEL_NAMES={
    "MistralAI(mistral-small-3.1-24b)": "mistralai/mistral-small-3.1-24b-instruct:free",
    "Google(gemma-3-27b)": "google/gemini-2.5-pro-exp-03-25:free",
    "Google(gemini-2.5-pro)":"google/gemma-3-27b-it:free",
    "Meta(llama-3.3-70b)":"meta-llama/llama-3.3-70b-instruct:free",
    "Deepseek(deepseek-chat-v3-0324)":"deepseek/deepseek-chat-v3-0324:free",
    "Qwen(qwen2.5-vl-32b)":"qwen/qwen2.5-vl-32b-instruct:free"
}


def show_info_messagebox(text, title):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setText(text)
    msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    msg.setWindowTitle(title)
    msg.setStandardButtons(QMessageBox.Ok)
    # start the app
    retval = msg.exec_()


def clean_code_for_prompt(code):
    """
    Removes comments and assert statements from Python code to create cleaner prompts.

    Args:
        code (str): The original Python code

    Returns:
        str: Cleaned code without comments and assert statements
    """
    # Parse line by line
    lines = code.split('\n')
    cleaned_lines = []

    # Track if we're inside a multi-line string
    in_multiline = False
    multiline_quote = None

    for line in lines:
        # Skip processing if inside a multi-line string
        if in_multiline:
            # Check if this line ends the multi-line string
            if multiline_quote in line:
                # Find the last occurrence of the closing quotes
                end_index = line.rindex(multiline_quote)
                # Check if these are actually closing quotes (not escaped)
                if not (end_index > 0 and line[end_index - 1] == '\\'):
                    in_multiline = False
            continue

        # Skip empty lines or lines with only whitespace
        if not line.strip():
            cleaned_lines.append('')
            continue

        # Skip full-line comments
        if line.strip().startswith('#'):
            continue

        # Check for multi-line string start
        stripped = line.strip()
        if (stripped.startswith('"""') or stripped.startswith("'''")) and not stripped.endswith(stripped[:3]) or \
                ('"""' in stripped and not stripped.endswith('"""') and stripped.count('"""') % 2 != 0) or \
                ("'''" in stripped and not stripped.endswith("'''") and stripped.count("'''") % 2 != 0):
            in_multiline = True
            multiline_quote = stripped[:3]
            continue

        # Skip assert statements
        if line.strip().startswith('assert '):
            continue

        # Remove inline comments
        code_part = line
        if '#' in line:
            # Don't remove # in strings
            in_string = False
            string_char = None
            comment_pos = -1

            for i, char in enumerate(line):
                # Toggle string state
                if char in ['"', "'"]:
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and (i == 0 or line[i - 1] != '\\'):
                        in_string = False

                # Find comment outside of string
                if char == '#' and not in_string:
                    comment_pos = i
                    break

            if comment_pos >= 0:
                code_part = line[:comment_pos].rstrip()

        # If there's still code left after removing comments
        if code_part.strip():
            cleaned_lines.append(code_part)

    # Join the cleaned lines
    return '\n'.join(cleaned_lines)

class CloudCompareAI:
    """
    Integrates CloudCompare with OpenRouter's LLM API (using Gemini) to provide intelligent
    code generation and assistance for CloudCompare Python API.
    """

    def __init__(self,
                 api_key,
                 set_model,#callback function: model="deepseek/deepseek-chat-v3-0324:free",
                 api_base_url="https://openrouter.ai/api/v1",
                 # model="google/gemini-2.5-pro-exp-03-25:free",
                 site_url="https://cloudcompare.org",
                 site_name="CloudCompare AI Assistant",
                 api_docs_path="cloudcompare_api.json"
                 ):

        self.api_key = api_key
        self.api_base_url = api_base_url
        self.set_model = set_model
        self.site_url = site_url
        self.site_name = site_name
        self.api_docs_path = api_docs_path

        # Load the API docs
        self.api_docs = self._load_api_docs()

        # Initialize the client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base_url
        )

        # Track conversation history
        self.conversation_history = []

    def _load_api_docs(self):
        """Load API documentation from JSON file"""
        if not os.path.exists(self.api_docs_path):
            # show_info_messagebox("WARNING: API documentation file not found at {self.api_docs_path}","Info")
            print(f"WARNING: API documentation file not found at {self.api_docs_path}")
            return {}

        with open(self.api_docs_path, 'r') as f:
            # show_info_messagebox("Loading API documentation file","Info")
            return json.load(f)

    def generate_system_prompt(self):
        """Generate a system prompt based on the API documentation"""
        prompt = """You are an AI assistant specialized in the CloudCompare 3D point cloud and mesh processing software.
You provide expert guidance on using CloudCompare's Python API (pycc and cccorelib modules) to manipulate and process 3D data.

When asked to generate code, please follow these guidelines:
1. Always include the necessary imports (import pycc, import cccorelib)
2. Use the correct CloudCompare Python API syntax and methods
3. Never add comments
4. Do not handle errors and do not check point cloud types; be simple and accurate
5. Follow the provided example practices

Key information about CloudCompare's Python API:
- pycc.GetInstance() is used to get the main CloudCompare instance
- Most operations require accessing entities (point clouds, meshes) through the CC instance
- You can use cc.getSelectedEntities() to get currently selected items
- After making changes, use cc.updateUI() and cc.redrawAll() to refresh the view
"""

        # # Add module summaries if available
        # if "modules" in self.api_docs:
        #     prompt += "\nAvailable modules:\n"
        #
        #     # Add pycc info
        #     if "pycc" in self.api_docs["modules"]:
        #         pycc_info = self.api_docs["modules"]["pycc"]
        #         prompt += f"\n## pycc Module\n{pycc_info.get('description', 'No description available')}\n"
        #
        #         # Add key classes
        #         if "classes" in pycc_info and pycc_info["classes"]:
        #             prompt += "\nKey classes:\n"
        #             for class_name, class_info in list(pycc_info["classes"].items())[:10]:
        #                 prompt += f"- {class_name}: {class_info.get('description', 'No description')[:100]}...\n"
        #
        #         # Add key functions
        #         if "functions" in pycc_info and pycc_info["functions"]:
        #             prompt += "\nKey functions:\n"
        #             for func_name, func_info in list(pycc_info["functions"].items())[:10]:
        #                 prompt += f"- {func_name}: {func_info.get('description', 'No description')[:100]}...\n"
        #
        #     # Add cccorelib info
        #     if "cccorelib" in self.api_docs["modules"]:
        #         cccorelib_info = self.api_docs["modules"]["cccorelib"]
        #         prompt += f"\n## cccorelib Module\n{cccorelib_info.get('description', 'No description available')}\n"
        #
        #         # Add key classes
        #         if "classes" in cccorelib_info and cccorelib_info["classes"]:
        #             prompt += "\nKey classes:\n"
        #             for class_name, class_info in list(cccorelib_info["classes"].items())[:10]:
        #                 prompt += f"- {class_name}: {class_info.get('description', 'No description')[:100]}...\n"
        #
        #         # Add key functions
        #         if "functions" in cccorelib_info and cccorelib_info["functions"]:
        #             prompt += "\nKey functions:\n"
        #             for func_name, func_info in list(cccorelib_info["functions"].items())[:10]:
        #                 prompt += f"- {func_name}: {func_info.get('description', 'No description')[:100]}...\n"

        # # Add instance methods summary if available
        # if "instance_methods" in self.api_docs and "methods" in self.api_docs["instance_methods"]:
        #     instance_methods = self.api_docs["instance_methods"]["methods"]
        #     prompt += "\n## CloudCompare Instance Methods (cc = pycc.GetInstance())\n"
        #
        #     for method_name, method_info in list(instance_methods.items())[:20]:
        #         prompt += f"- cc.{method_name}: {method_info.get('description', 'No description')[:100]}...\n"

        # # Add workflow examples if available
        # if "workflows" in self.api_docs and self.api_docs["workflows"]:
        #     prompt += "\n## Common CloudCompare Python Workflows\n"
        #
        #     # Add up to 5 workflow examples
        #     for i, (workflow_name, workflow) in enumerate(list(self.api_docs["workflows"].items())[:5]):
        #         prompt += f"\n### {workflow.get('name', workflow_name)}\n"
        #         prompt += f"{workflow.get('description', 'No description available')}\n"
        #         prompt += "```python\n"
        #
        #         # Truncate very long code examples
        #         code = workflow.get('code_example', '# No code example available')
        #         if len(code) > 1000:
        #             lines = code.split('\n')
        #             if len(lines) > 30:
        #                 prompt += '\n'.join(lines[:30]) + '\n# ... additional code truncated ...\n'
        #             else:
        #                 prompt += code[:1000] + '\n# ... additional code truncated ...\n'
        #         else:
        #             prompt += code
        #
        #         prompt += "\n```\n"

        # show_info_messagebox(prompt,"system prompts")

        return prompt

    def find_relevant_examples(self, query, top_n=5):
        """Find relevant example workflows for a given query"""
        if "workflows" not in self.api_docs or not self.api_docs["workflows"]:
            return []

        # Simple keyword matching for now
        relevant = []
        query_words = set(query.lower().split())

        for workflow_name, workflow in self.api_docs["workflows"].items():
            score = 0

            # Check name and description
            name = workflow.get('name', '').lower()
            description = workflow.get('description', '').lower()

            for word in query_words:
                if word in name:
                    score += 3
                if word in description:
                    score += 2
                if any(word in trigger.lower() for trigger in workflow.get('natural_language_triggers', [])):
                    score += 2

            if score > 0:
                relevant.append((workflow, score))

        # Sort by relevance score
        relevant.sort(key=lambda x: x[1], reverse=True)

        return [item[0] for item in relevant[:top_n]]

    def query(self, user_input, include_history=False, max_tokens=4096, temperature=0.3):
        """
        Send a query to the LLM and get a response
        """
        # Add user input to conversation history
        self.conversation_history.append({"role": "user", "content": user_input})

        # Find relevant examples and references
        relevant_examples = self.find_relevant_examples(user_input)

        # Create messages array
        messages = [
            {"role": "system", "content": self.generate_system_prompt()}
        ]

        # Add conversation history if requested
        if include_history and len(self.conversation_history) > 2:
            # Add last 5 messages (or fewer if not available)
            history_to_include = self.conversation_history[:-1][-5:]
            messages.extend(history_to_include)

        # Add current user input with relevant context
        content = user_input

        if relevant_examples:
            content += "\n\nHere are some relevant CloudCompare workflows that might help:\n\n"
            for i, example in enumerate(relevant_examples):
                content += f"Example {i + 1}: {example.get('name', 'Example')}\n"
                content += f"{example.get('description', 'No description')}\n"
                content += "```python\n"

                # Truncate very long code examples
                code = example.get('code_example', '# No code available')
                # if len(code) > 1000:
                #     lines = code.split('\n')
                #     if len(lines) > 30:
                #         content += '\n'.join(lines[:30]) + '\n# ... additional code truncated ...\n'
                #     else:
                #         content += code[:1000] + '\n# ... additional code truncated ...\n'
                # else:
                #     content += code
                content += clean_code_for_prompt(code)
                content += "\n```\n\n"

        messages.append({"role": "user", "content": content})
        # show_info_messagebox(f"{content}", "Info")
        # with open("content.txt", "w") as text_file:
        #     text_file.write(content)

        try:
            # Call the OpenRouter API with Gemini model
            response = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": self.site_url,  # Site URL for rankings on openrouter.ai
                    "X-Title": self.site_name,  # Site title for rankings on openrouter.ai
                },
                extra_body={},
                model=self.set_model(),
                messages=messages,
                temperature=temperature,
                # max_tokens=max_tokens,
                stream=False
            )

            # Extract the response
            response_text = response.choices[0].message.content

            # Add to conversation history
            self.conversation_history.append({"role": "assistant", "content": response_text})

            return response_text

        except Exception as e:
            error_msg = f"Error querying LLM: {str(e)}"
            print(error_msg)

            # Add error to conversation history
            self.conversation_history.append({"role": "assistant", "content": error_msg})

            return error_msg

    def execute_code(self, code):
        """
        Execute Python code directly in CloudCompare's Python console environment
        """
        try:
            # The code will run in the current CloudCompare Python environment
            # which already has access to pycc, cccorelib, etc.
            exec(code)

            return "Code executed successfully in CloudCompare environment"

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return f"Error executing code: {str(e)}\n\n{error_details}"
class ChatMessage(QWidget):
    """Widget to display a single message in the chat window"""

    def __init__(self, text, is_user=True, parent=None):
        super().__init__(parent)
        self.init_ui(text, is_user)
        self.setFixedHeight(150)

    def init_ui(self, text, is_user):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)

        # Add sender label (User or Assistant)
        sender_label = QLabel("You" if is_user else "Assistant")
        sender_label.setStyleSheet(f"""
            font-weight: bold;
            color: {'#4a76a8' if is_user else '#8a8a8a'};
        """)
        layout.addWidget(sender_label)

        # Add message content
        message_label = QLabel(text)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        message_label.setStyleSheet("""
            background-color: #f5f5f5;
            border-radius: 8px;
            padding: 2px;
        """)
        layout.addWidget(message_label)

        # Set the layout for this widget
        self.setLayout(layout)

        # Style based on sender
        if is_user:
            self.setStyleSheet("""
                background-color: #f0f7ff;
                border-radius: 5px;
                margin: 2px 20px 2px 2px;
            """)
        else:
            self.setStyleSheet("""
                background-color: #ffffff;
                border-radius: 5px;
                margin: 2px 2px 2px 20px;
            """)


class ChatHistoryItem(QWidget):
    """Custom widget for displaying a chat session in the history sidebar"""
    clicked = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)

    def __init__(self, chat_id, title, parent=None):
        super().__init__(parent)
        self.chat_id = chat_id
        self.title = title
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        # layout.setContentsMargins(5, 5, 5, 5)
        layout.setContentsMargins(0, 0, 0, 0)

        # Chat title
        title_label = QLabel(self.title)
        font = title_label.font()
        font.setPointSize(12)  # Increase font size
        title_label.setStyleSheet("color: #333333;")
        layout.addWidget(title_label, 1)


        # Delete button
        delete_icon = self.style().standardIcon(QStyle.SP_DialogCloseButton)
        delete_button = QtWidgets.QPushButton()
        delete_button.setIcon(delete_icon)
        # delete_button.setIcon(QIcon.fromTheme("edit-delete"))
        delete_button.setFixedSize(24, 24)
        delete_button.setToolTip("Delete this chat")
        delete_button.clicked.connect(self._on_delete_clicked)
        layout.addWidget(delete_button, 0)

        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                border-radius: 4px;
                height: 30px;
                padding: 0px;
                margin: 0px;
            }
            QWidget:hover {
                background-color: #e0e0e0;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.chat_id)
        super().mousePressEvent(event)

    def _on_delete_clicked(self):
        self.delete_clicked.emit(self.chat_id)

#
class ChatWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(ChatWindow,self).__init__()
        # Load the UI file
        uic.loadUi(os.path.join(Path(__file__).parent.resolve(), 'form.ui'), self)

        # Set the window size larger
        self.resize(600, 800)

        # Increase font sizes
        app = QApplication.instance()
        font = app.font()
        font.setPointSize(12)  # Increase base font size
        app.setFont(font)

        # Add the title label
        self.title_label = QLabel("CloudCompare LLM AI Integration Demo (by Zhouxin Xi)")
        font = self.title_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #4a76a8; margin: 10px;")

        # Configure the input text box for text wrapping
        self.messageInput.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self.messageInput.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.messageInput.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)

        # Create model selector combo box
        self.model_selector = QtWidgets.QComboBox()
        self.model_selector.addItems(MODEL_NAMES.keys())
        self.model_selector.setCurrentIndex(0)  # Default to first model
        font = self.model_selector.font()
        font.setPointSize(12)
        self.model_selector.setFont(font)
        self.model_selector.setMinimumHeight(40)

        self.model_selector.setStyleSheet("""
            QComboBox {
                border: 1px solid #cccccc;
                border-radius: 5px;
                min-width: 200px;
            }
        """)

        # Create a widget to hold the selector and label
        self.header_widget = QWidget()
        self.header_layout = QVBoxLayout(self.header_widget)
        self.header_layout.addWidget(self.title_label)

        self.selector_layout = QHBoxLayout()
        self.selector_layout.addWidget(QLabel("Select AI Model:"))
        self.selector_layout.addWidget(self.model_selector, 1)  # Give combo box stretch

        self.header_layout.addLayout(self.selector_layout)

        # Insert the header widget at the top of the chat widget layout
        chat_layout = self.chatWidget.layout()
        chat_layout.insertWidget(0, self.header_widget)

        # Initialize variables
        self.chat_history = {}  # Dictionary to store chat sessions
        self.current_chat_id = None

        # Connect signals to slots
        self.newChatBtn.clicked.connect(self.start_new_chat)
        self.sendButton.clicked.connect(self.send_message)

        # Initialize status bar with current model
        self.update_status_bar("Ready")

        # Connect menu actions
        self.actionNew_Chat.triggered.connect(self.start_new_chat)
        # self.actionSave_Chats.triggered.connect(lambda: self.save_chats())
        # self.actionLoad_Chats.triggered.connect(lambda: self.load_chats())
        self.actionExit.triggered.connect(QCoreApplication.quit)

        # Create CloudCompare AI instance
        self.CC_AI = CloudCompareAI(
            api_key=OPENAI_API_KEY,
            set_model=lambda: MODEL_NAMES[self.model_selector.currentText()],
            api_base_url=OPENAI_API_BASE,
            api_docs_path=LOCAL_API_DOCS
        )

        # Initialize with a new chat
        self.start_new_chat()

    def update_status_bar(self,messsage_status):
        """Update the status bar with the current model selection"""
        # selected_model = self.model_selector.currentText()
        self.statusbar.showMessage(messsage_status)

    def adjust_input_height(self):
        """Dynamically adjust the height of the input text field based on content"""
        document_height = self.messageInput.document().size().height()
        new_height = min(document_height + 20, 150)  # Maximum height of 150px
        self.messageInput.setMinimumHeight(new_height)

    def start_new_chat(self):
        """Create a new chat session"""
        # Generate a unique ID for the chat
        chat_id = f"chat_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        timestamp = datetime.datetime.now().strftime("%H:%M")
        title = f"New Chat ({timestamp})"

        # Initialize the chat session
        self.chat_history[chat_id] = {
            "title": title,
            "messages": []
        }

        # Add to history sidebar
        self.add_chat_to_history(chat_id, title)

        # Switch to the new chat
        self.switch_to_chat(chat_id)

    def add_chat_to_history(self, chat_id, title):
        """Add a chat session to the history sidebar"""
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 40))

        chat_item_widget = ChatHistoryItem(chat_id, title)
        chat_item_widget.clicked.connect(self.switch_to_chat)
        chat_item_widget.delete_clicked.connect(self.delete_chat)

        self.historyList.addItem(item)
        self.historyList.setItemWidget(item, chat_item_widget)

    def switch_to_chat(self, chat_id):
        """Switch to a different chat session"""
        # Clear current messages
        self.clear_messages()

        # Update current chat ID
        self.current_chat_id = chat_id

        # Load messages for this chat
        if chat_id in self.chat_history:
            for msg in self.chat_history[chat_id]["messages"]:
                self.display_message(msg["text"], msg["is_user"])

    def clear_messages(self):
        """Clear all messages from the display"""
        while self.messagesLayout.count():
            item = self.messagesLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def delete_chat(self, chat_id):
        """Delete a chat session"""
        # Remove from history dictionary
        if chat_id in self.chat_history:
            del self.chat_history[chat_id]

        # Remove from UI
        for i in range(self.historyList.count()):
            item = self.historyList.item(i)
            widget = self.historyList.itemWidget(item)
            if isinstance(widget, ChatHistoryItem) and widget.chat_id == chat_id:
                self.historyList.takeItem(i)
                break

        # If we deleted the current chat, start a new one
        if chat_id == self.current_chat_id:
            if self.historyList.count() > 0:
                # Switch to the first available chat
                item = self.historyList.item(0)
                widget = self.historyList.itemWidget(item)
                self.switch_to_chat(widget.chat_id)
            else:
                # No chats left, create a new one
                self.start_new_chat()

    def format_for_cloudcompare_exec(self,llm_code):
        """
        Converts LLM-generated code to a format that works with CloudCompare's exec() function.

        Args:
            llm_code (str): The code string from an LLM (may have escaped newlines)

        Returns:
            str: Formatted code string ready for exec()
        """
        # Handle different input formats
        if not isinstance(llm_code, str):
            llm_code = str(llm_code)

        # Extract the code content from any string formatting
        code_content = llm_code

        # If it's wrapped in exec()
        if code_content.startswith("exec(") and code_content.endswith(")"):
            code_content = code_content[5:-1].strip()

        # Remove surrounding quotes
        if "\\n" in code_content:
            # Has escaped newlines
            if (code_content.startswith('"') and code_content.endswith('"')) or \
                    (code_content.startswith("'") and code_content.endswith("'")):
                code_content = code_content[1:-1]

            # Replace escaped characters
            code_content = code_content.replace('\\"', '"').replace("\\'", "'")
            code_content = code_content.replace("\\n", "\n")
        elif (code_content.startswith('"""') and code_content.endswith('"""')) or \
                (code_content.startswith("'''") and code_content.endswith("'''")):
            # Already in triple quotes
            code_content = code_content[3:-3]
        elif (code_content.startswith('"') and code_content.endswith('"')) or \
                (code_content.startswith("'") and code_content.endswith("'")):
            # Single-quoted string
            code_content = code_content[1:-1]

        # Split into lines for processing
        lines = code_content.split("\n")

        # Process each line
        processed_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:  # Empty line
                processed_lines.append("")
                continue

            # Count leading spaces to check for indentation
            leading_spaces = len(line) - len(stripped)

            if leading_spaces >= 4:
                # This appears to be an indented block - preserve indentation
                processed_lines.append(line)
            else:
                # Main code line - remove leading spaces
                processed_lines.append(stripped)

        # Join the processed lines
        final_code = "\n".join(processed_lines)

        # Format for exec with triple quotes
        return f"""{final_code}"""
    def send_message(self):
        """Send a message and process the response"""
        message_text = self.messageInput.toPlainText().strip()#Example: Please create a height ramp for the selected point cloud.
        if not message_text:
            return

        # Clear input field
        self.messageInput.clear()

        # Display user message
        self.display_message(message_text, True)

        # Save to history
        if self.current_chat_id in self.chat_history:
            self.chat_history[self.current_chat_id]["messages"].append({
                "text": message_text,
                "is_user": True,
                "timestamp": datetime.datetime.now().isoformat()
            })

            # Update chat title if it's the first message
            if len(self.chat_history[self.current_chat_id]["messages"]) == 1:
                # Use the first part of the message as the title
                title = (message_text[:20] + "...") if len(message_text) > 20 else message_text
                self.chat_history[self.current_chat_id]["title"] = title

                # Update the title in the history list
                self.update_chat_title(self.current_chat_id, title)

        self.update_status_bar("Message sent to LLM...")
        self.handle_response(self.CC_AI.query(message_text))

        # Generate fake response for testing only
        # self.generate_fake_response(message_text)

    def handle_response(self,response_text):

        # Check for code blocks
        code_blocks = re.findall(r"```python\s+(.*?)\s+```", response_text, re.DOTALL)
        # self.show_info_messagebox(code_blocks[0], "Info")
        if code_blocks:
            last_code_block = code_blocks[0]

            self.display_message(last_code_block, False)
            if self.current_chat_id in self.chat_history:
                self.chat_history[self.current_chat_id]["messages"].append({
                    "text": last_code_block,
                    "is_user": False,
                    "timestamp": datetime.datetime.now().isoformat()
                })

            self.update_status_bar("Resonse received...")
            formatted_code = self.format_for_cloudcompare_exec(last_code_block)
            exec(formatted_code)

            self.update_status_bar("Executed.")
            self.save_chats()


    def generate_fake_response(self, user_message):
        """Generate a fake response to the user's message"""
        # Create a simple fake response
        response_text = f"This is the answer to: {user_message}"

        # Display the response
        self.display_message(response_text, False)

        # Save to history
        if self.current_chat_id in self.chat_history:
            self.chat_history[self.current_chat_id]["messages"].append({
                "text": response_text,
                "is_user": False,
                "timestamp": datetime.datetime.now().isoformat()
            })

        self.update_status_bar("Resonse received.")


    def update_chat_title(self, chat_id, new_title):
        """Update the title of a chat in the history sidebar"""
        for i in range(self.historyList.count()):
            item = self.historyList.item(i)
            widget = self.historyList.itemWidget(item)
            if isinstance(widget, ChatHistoryItem) and widget.chat_id == chat_id:
                widget.title = new_title
                widget.findChild(QLabel).setText(new_title)
                break

    def display_message(self, text, is_user):
        """Display a message in the chat window"""
        message_widget = ChatMessage(text, is_user)
        self.messagesLayout.addWidget(message_widget)

        # Scroll to the bottom
        QApplication.processEvents()  # Process pending events to update scroll area
        self.messagesArea.verticalScrollBar().setValue(
            self.messagesArea.verticalScrollBar().maximum()
        )


    def save_chats(self, filename="chat_history.json"):
        """Save all chat sessions to a file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.chat_history, f)
        except Exception as e:
            print(f"Error saving chats: {e}")

    def load_chats(self, filename="chat_history.json"):
        """Load chat sessions from a file"""
        try:
            with open(filename, 'r') as f:
                loaded_history = json.load(f)
                self.chat_history = loaded_history

                # Rebuild the history sidebar
                self.historyList.clear()
                for chat_id, chat_data in self.chat_history.items():
                    self.add_chat_to_history(chat_id, chat_data["title"])

                # Load the first chat
                if self.chat_history:
                    first_chat_id = next(iter(self.chat_history))
                    self.switch_to_chat(first_chat_id)
        except FileNotFoundError:
            # No saved history, just continue with a new chat
            pass
        except Exception as e:
            print(f"Error loading chats: {e}")

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    window = ChatWindow()
    window.show()

    # Try to load previous chats
    window.load_chats()

    # Save chats when the application exits
    app.aboutToQuit.connect(lambda: window.save_chats())

    sys.exit(app.exec_())
