# Houdini-LLM: True Agentic TD

Houdini-LLM is an advanced, AI-powered Technical Director (TD) Agent built directly into SideFX Houdini. Rather than just being a chatbot that answers questions, Houdini-LLM is a **"True Agentic" system** capable of analyzing your scene, writing custom Python tools, executing them inside Houdini, and *learning* from its successes.

---

## 🌟 Key Features & Architecture

### 1. Human-in-the-Loop (HITL) Execution
We believe AI should assist, not override. Houdini-LLM will never modify your scene without permission. 
- When the agent writes a script to solve your problem, it triggers a **Review Panel**. 
- You can review the code and must explicitly click **[✅ Approve & Run]** or **[❌ Reject]**.
- Once approved, the code executes safely inside a Houdini Undo block.

### 2. Specialized Agents (Personas)
Instead of a generic "jack of all trades" AI, you can select specific "Brains" from the Persona dropdown:
- **General TD:** Excellent for pipeline tasks, node creation, and generic python scripts.
- **Arnold Expert:** Loaded with specific context for Arnold rendering.
- **Solaris/USD Expert:** Specialized in LOPs and USD stage manipulation.
- **FX Expert:** Focused on Vellum, Pyro, and complex simulation setups.
*(Note: You can turn off the "Agent Mode Auto" checkbox at any time to make the AI purely conversational/read-only!)*

### 3. Hermes-style Self-Learning Loop (`ReflectionWorker`)
Houdini-LLM learns from you. If the agent gives you a script that fails 5 times but succeeds on the 6th try, we don't want it memorizing the failures. 
- When a script finally works perfectly, you click **[🌟 Save to Memory]** inside the chat UI.
- This triggers our hidden **`ReflectionWorker`**, which runs in the background. It analyzes the code, summarizes what it does, and generates a mathematical vector embedding of the logic.

### 4. Vector Database Memory (`sqlite-vec`)
All of your conversations and saved skills are stored permanently in a fast, local SQLite database (`C:\Users\<User>\houdini_ai_agent_memory`). 
- We use **`sqlite-vec`** to power Lightning-fast Semantic Vector Search. 
- When you ask a new question, the agent searches this database for its own past successful scripts and uses them as reference, meaning **the agent gets smarter the more you use it.**

---

## 🚀 Installation Instructions

We have designed the installation to be as simple as possible. You can extract the project anywhere on your hard drive.

### Step 1: Download & Extract
Download or clone this repository and extract it anywhere on your computer. 
*(For example: `D:\dev\applications\Houdini-LLM`)*

### Step 2: Install Dependencies (One-time Setup)
The plugin requires the `sqlite-vec` library for its long-term vector memory. We have included an automated script to handle this safely without breaking your Houdini environment.

1. Open the **Houdini Command Line Tools** from your Windows Start Menu (this ensures the internal `hython` command is available).
2. Use `cd` to navigate to the folder where you extracted the project.
   *(Example: `cd D:\dev\applications\Houdini-LLM`)*
3. Run the installer script:
   `install_dependencies.bat`

*This will safely download the required libraries into a local `python_libs` folder inside your repository.*

### Step 3: Build the RAG Knowledge Base (One-time Setup)
To give the AI Agent its deep knowledge of Houdini's Python API, VEX, and nodes, you need to build the vector database.
1. Simply double-click `build_rag_database.bat` in the root folder.
2. Wait for the terminal to finish generating the database embeddings.
*(This is a one-time process. It will skip automatically if you run it twice!)*

### Step 4: Tell Houdini Where the Plugin Is
Houdini uses `.json` package files to load custom plugins.

1. Open your Houdini preferences directory (usually located at `Documents/houdini20.0/` or similar depending on your version).
2. Open the `packages` folder. (Create a folder named `packages` if it doesn't exist).
3. Copy the `Houdini-LLM.json` file from your downloaded repository and paste it into this `packages` folder.
4. **Important:** Open that pasted `Houdini-LLM.json` file in any text editor and change the `HOUDINI_LLM_ROOT` path to point exactly to where you extracted the folder in Step 1.

*Example of the edited JSON:*
```json
{
    "env": [
        {
            "HOUDINI_LLM_ROOT": "C:/path/to/where/you/extracted/Houdini-LLM"
        },
        {
            "PYTHONPATH": [
                "$HOUDINI_LLM_ROOT/scripts/python",
                "$HOUDINI_LLM_ROOT/python_libs"
            ]
        }
    ],
    "path": "$HOUDINI_LLM_ROOT"
}
```
*(Make sure to use forward slashes `/` in the path!)*

### Step 5: Run Houdini
1. Start Houdini.
2. Open a new **Python Panel** tab in your layout.
3. Select **AI TD Agent** from the interface dropdown.
4. Click the ⚙ (Gear) icon to configure your API key, and you are ready to go!

---

## 📚 Deep Dive Documentation

If you want to understand exactly how the internal architecture, intelligent RAG chunking, and code execution loops work under the hood, check out our dedicated documentation:
- **[Agentic Workflow & Architecture](agentic_workflow.md)**
- **[Agent Flow Deep Dive: Embeddings, Memory & Self-Learning](agent_flow_deep_dive.md)**
