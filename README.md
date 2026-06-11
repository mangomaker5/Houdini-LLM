# Houdini-LLM: True Agentic TD

Houdini-LLM is an advanced, AI-powered Technical Director (TD) Agent built directly into SideFX Houdini. Rather than just being a chatbot that answers questions, Houdini-LLM is a **"True Agentic" system** capable of analyzing your scene, writing custom Python tools, executing them inside Houdini, and *learning* from its successes.

The entire system is built around one rule: **Never Guess.**
LLMs often hallucinate parameter names and API calls. Houdini-LLM eliminates guessing by forcing the agent to **inspect before it acts** and **learn from every outcome** via a strict Inspect → Draft → Review → Execute pipeline.

---

## 🌟 Key Features & Architecture

### 1. Human-in-the-Loop (HITL) Execution
We believe AI should assist, not override. Houdini-LLM will never modify your scene without permission. 
- When the agent drafts a script to solve your problem, it triggers a **Yellow Review Panel**. 
- You can review the proposed code and must explicitly click **[✅ Approve & Run]**, **[❌ Reject]**, or **[Retry]**.
- Once approved, the code executes safely inside a `hou.undos.group` so you can always `Ctrl+Z` the results.

### 2. Hybrid Search Engine & RAG
The agent maintains its own localized knowledge base powered by `sqlite-vec`. Every search uses a dual-path strategy:
- **Vector Search (L2 Distance)**: For semantic similarity.
- **Keyword Search (FTS5)**: For exact API and syntax matches.
- **Reciprocal Rank Fusion (RRF)**: Mathematically fuses both lists so neither path dominates, ensuring pinpoint accuracy.

### 3. Hermes-style Self-Learning Loop (`ReflectionWorker`)
Houdini-LLM learns from you. 
- When a script finally works perfectly, you click **[🌟 Save to Memory]** inside the chat UI.
- A hidden **`ReflectionWorker`** runs in the background. It analyzes the code, summarizes what it does, and embeds it into your Vector DB.
- **Deduplication:** The system checks for semantic duplicates before saving. If an improved version of an old script is saved, the memory is updated rather than cluttered.

### 4. Anti-Patterns
If you approve a script but it **crashes** during execution inside Houdini, the agent automatically intercepts the Python traceback.
- The error is converted into an **Anti-Pattern** and permanently saved to the Vector DB.
- The next time the agent tries a similar task, it sees its past mistake and self-corrects before writing the code.

### 5. Specialized Agents (Personas)
Select specific "Brains" from the Persona dropdown depending on your task:
- **General TD:** Excellent for pipeline tasks, node creation, and generic python scripts.
- **Arnold Expert:** Loaded with specific context for Arnold rendering.
- **Solaris/USD Expert:** Specialized in LOPs and USD stage manipulation.
- **FX Expert:** Focused on Vellum, Pyro, and complex simulation setups.

### 6. Context Management
Use the `/compact` command at any time. Old chat messages are routinely summarized and trimmed to free up token space. However, **your Vector DB Memory (Skills and Anti-Patterns) remains permanent** and unaffected by compaction.

### 7. Scene Context Awareness
The agent automatically reads whatever node is currently selected in your Houdini Network View. **Best Practice:** Select the node you want to work on first, and then ask the agent to modify it!

### 8. Managing Your Memory
Your Vector Database is fully under your control. Use the **Manage Memory** button in the UI at any time to view, review, and delete your saved skills and anti-patterns.

---

## 🚀 Detailed Setup Flow

Follow these steps to set up Houdini-LLM on your machine.

### Step 1: Download & Extract
Download or clone this repository and extract it anywhere on your computer. 
*(For example, the developer's local setup is at `D:\dev\applications\Houdini-LLM`)*

> [!TIP]
> **We recommend keeping this out of your `C:` drive** (e.g., use a `D:` or `E:` drive) to save system disk space and avoid any strict Windows permission issues when building the local vector database.

### Step 2: Install Python Dependencies
The plugin requires `sqlite-vec` (for vector memory) and `pygments` (for syntax highlighting).
1. Open the **Houdini Command Line Tools** from your Windows Start Menu (this ensures the internal `hython` command is used, not your system Python).
2. Navigate to where you extracted the project:
   ```cmd
   cd D:\dev\applications\Houdini-LLM
   ```
3. Run the automated installer script:
   ```cmd
   install_dependencies.bat
   ```
*This safely downloads the required libraries into a local `python_libs` folder inside your repository without touching Houdini's core files.*

### Step 3: Build the RAG Knowledge Base
To give the AI Agent its deep knowledge of Houdini's Python API, you need to build the initial vector database.
1. Simply double-click `build_rag_database.bat` in the root folder.
2. Wait for the terminal to finish generating the database embeddings.
*(This is a one-time process. It will skip automatically if you run it twice!)*

### Step 4: Configure Houdini Packages
Houdini uses `.json` package files to load custom plugins.
1. Open your Houdini preferences directory (usually `Documents/houdini20.0/` or similar depending on your version).
2. Open the `packages` folder (create one if it doesn't exist).
3. Copy the `Houdini-LLM.json` file from your downloaded repository into the `packages` folder.
4. **Important:** Open the pasted `Houdini-LLM.json` file in a text editor and update the `HOUDINI_LLM_ROOT` path to point exactly to where you extracted the folder in Step 1. Every user must manually update this path so Houdini knows where to load the scripts from.

*Example of the edited JSON (make sure to use forward slashes `/` - e.g. `D:/dev/applications/Houdini-LLM`):*
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

### Step 5: API Key Setup & Run
1. Start Houdini.
2. Open a new **Python Panel** tab in your layout.
3. Select **AI TD Agent** from the interface dropdown.
4. Click the **⚙ (Gear)** icon at the top right of the agent panel to enter your **OpenRouter API key**. 
   - You can get an API key by signing up at [OpenRouter.ai](https://openrouter.ai/).
   - Our default configured chat model is **`deepseek/deepseek-v4-pro`**, which is optimized for agentic coding.
   - The plugin also utilizes a separate embedded model from OpenAI (`openai/text-embedding-3-small`) via OpenRouter to generate the vector memory for self-learning and RAG. Ensure your account has sufficient credits.
5. You're ready to go! Start chatting with the agent.

---

## 🛠️ Advanced Setup: Customizing RAG Ingestion

If you want to ingest additional custom Houdini Help documentation into the agent's brain, you can manually update the RAG system:

1. Open `scripts/python/rag/ingest.py`.
2. Locate the `critical_zips` dictionary (around line 217). 
3. Add your new help folder `.zip` file mapping. Ensure your `base_help_dir` path correctly points to your Houdini installation.
4. **Important Rules:**
   - **Do not modify the core ingestion logic.** Just add keys to the dictionary.
   - **Process strictly 1 by 1.** When you run the ingestor, select and process one `.zip` at a time to prevent API timeouts or rate limits.
5. Re-run `build_rag_database.bat`. The script will detect your new additions and present them in the terminal list for ingestion.

---

## 📚 Deep Dive Documentation

If you want to understand exactly how the internal architecture, intelligent RAG chunking, and code execution loops work under the hood, check out our dedicated documentation:
- **[Agentic Workflow & Architecture](agentic_workflow.md)**
- **[Agent Flow Deep Dive: Embeddings, Memory & Self-Learning](agent_flow_deep_dive.md)**
