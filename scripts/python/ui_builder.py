from PySide6 import QtWidgets, QtCore
from components import ChatTextBrowser


class UIBuilderMixin:
    def init_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        # === Left Sidebar ===
        self.sidebar = QtWidgets.QWidget()
        self.sidebar.setObjectName("Sidebar")
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        self.new_chat_btn = QtWidgets.QPushButton("＋ New Session")
        self.new_chat_btn.setObjectName("NewChatButton")
        self.new_chat_btn.setToolTip("Start a new conversation session")
        self.new_chat_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.new_chat_btn.clicked.connect(self.on_new_chat)
        self.session_scroll = QtWidgets.QScrollArea()
        self.session_scroll.setObjectName("SessionScroll")
        self.session_scroll.setWidgetResizable(True)
        self.session_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.session_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.session_container = QtWidgets.QWidget()
        self.session_container.setObjectName("SessionContainer")
        self.session_layout = QtWidgets.QVBoxLayout(self.session_container)
        self.session_layout.setContentsMargins(0, 0, 0, 0)
        self.session_layout.setSpacing(2)
        self.session_layout.setAlignment(QtCore.Qt.AlignTop)
        self.session_scroll.setWidget(self.session_container)
        self.manage_memory_btn = QtWidgets.QPushButton("🧠 Manage Memory")
        self.manage_memory_btn.setObjectName("ManageMemoryButton")
        self.manage_memory_btn.setToolTip(
            "View and manage learned skills and code snippets"
        )
        self.manage_memory_btn.setCursor(QtCore.Qt.PointingHandCursor)

        sidebar_layout.addWidget(self.new_chat_btn)
        sidebar_layout.addWidget(self.manage_memory_btn)
        sidebar_layout.addWidget(self.session_scroll)
        # === Right Chat Area ===
        self.chat_area = QtWidgets.QWidget()
        chat_layout = QtWidgets.QVBoxLayout(self.chat_area)
        chat_layout.setContentsMargins(20, 20, 20, 20)
        chat_layout.setSpacing(15)
        top_bar = QtWidgets.QHBoxLayout()
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.model_combo.lineEdit().setPlaceholderText("Search models...")
        self.model_combo.lineEdit().setAlignment(QtCore.Qt.AlignLeft)
        self.model_combo.setToolTip("Select the LLM model to use")
        self.model_combo.setMinimumWidth(250)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        completer = QtWidgets.QCompleter()
        completer.setFilterMode(QtCore.Qt.MatchContains)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.model_combo.setCompleter(completer)
        self.settings_btn = QtWidgets.QPushButton("⚙ Settings")
        self.settings_btn.setObjectName("SettingsButton")
        self.settings_btn.setToolTip("Open application settings (API Keys, etc.)")
        self.settings_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        top_bar.addWidget(self.model_combo)
        top_bar.addStretch()
        top_bar.addWidget(self.settings_btn)
        self.chat_display = ChatTextBrowser()
        self.chat_display.document().setDefaultStyleSheet("")
        # Session Window Progress Bar (compact, left-aligned)
        ctx_bar = QtWidgets.QHBoxLayout()
        ctx_bar.setContentsMargins(0, 0, 0, 5)
        self.context_progress = QtWidgets.QProgressBar()
        self.context_progress.setObjectName("ContextProgressBar")
        self.context_progress.setTextVisible(True)
        self.context_progress.setFormat("Session: 0 / 128,000 tokens")
        self.context_progress.setMinimum(0)
        self.context_progress.setMaximum(128000)
        self.context_progress.setFixedHeight(18)
        self.context_progress.setMaximumWidth(280)
        self.context_progress.setToolTip(
            "Current session token usage against the context limit"
        )

        self.usage_label = QtWidgets.QLabel("💰 $0.00 · 0 tokens")
        self.usage_label.setStyleSheet(
            "color: #f1c40f; font-size: 10px; font-weight: bold; "
            "background-color: #2b2b2b; border: 1px solid #f1c40f; "
            "border-radius: 4px; padding: 2px 8px;"
        )
        self.usage_label.setFixedHeight(18)
        self.usage_label.setToolTip("Total application API cost and token consumption")

        ctx_bar.addWidget(self.context_progress)
        ctx_bar.addWidget(self.usage_label)
        ctx_bar.addStretch()
        # Command Autocomplete Popup
        self.cmd_popup = QtWidgets.QListWidget()
        self.cmd_popup.setObjectName("CommandPopup")
        self.cmd_popup.addItems(
            [
                "/compact - Force manual context summarization",
                "/usage - Show token usage and cost report",
                "/arnold - Route to Arnold Expert",
                "/fx - Route to FX Expert",
                "/solaris - Route to Solaris/USD Expert",
            ]
        )
        self.cmd_popup.setFixedHeight(125)
        self.cmd_popup.hide()
        self.cmd_popup.itemClicked.connect(self.on_cmd_popup_selected)
        # Input Area
        input_container = QtWidgets.QFrame()
        input_container.setObjectName("InputContainer")
        input_layout = QtWidgets.QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)
        self.text_input = QtWidgets.QTextEdit()
        self.text_input.setObjectName("InputTextEdit")
        self.text_input.setMaximumHeight(100)
        self.text_input.setPlaceholderText(
            "Type /arnold, /fx, /solaris for experts, or type normally for General TD..."
        )
        self.text_input.installEventFilter(self)
        self.text_input.textChanged.connect(self.on_text_changed)
        self.send_btn = QtWidgets.QPushButton("↑")
        self.send_btn.setObjectName("SendButton")
        self.send_btn.setToolTip("Send message to the agent")
        self.send_btn.setFixedSize(30, 30)
        self.send_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self.on_send_clicked)
        send_layout = QtWidgets.QVBoxLayout()
        send_layout.addStretch()
        send_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.text_input)
        input_layout.addLayout(send_layout)

        self.warning_label = QtWidgets.QLabel(
            "⚠️ WARNING: LLM-generated code and MCP actions may cause issues. Always backup or version-up your scene file to avoid data loss."
        )
        self.warning_label.setObjectName("WarningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setAlignment(QtCore.Qt.AlignCenter)

        # Review Panel
        self.review_panel = QtWidgets.QFrame()
        self.review_panel.setObjectName("ReviewPanel")
        review_layout = QtWidgets.QVBoxLayout(self.review_panel)
        self.review_label = QtWidgets.QLabel("Agent proposed code execution:")
        self.review_label.setObjectName("ReviewLabel")
        self.review_code = QtWidgets.QTextBrowser()
        self.review_code.setObjectName("CodePreview")
        self.review_code.setMinimumHeight(150)

        btn_layout = QtWidgets.QHBoxLayout()
        self.approve_btn = QtWidgets.QPushButton("✅ Approve & Run")
        self.approve_btn.setObjectName("ApproveBtn")
        self.approve_btn.setToolTip("Execute this code safely in Houdini")
        self.approve_btn.setCursor(QtCore.Qt.PointingHandCursor)

        self.reject_btn = QtWidgets.QPushButton("❌ Reject")
        self.reject_btn.setObjectName("RejectBtn")
        self.reject_btn.setToolTip("Reject this code and ask the agent to stop")
        self.reject_btn.setCursor(QtCore.Qt.PointingHandCursor)

        self.retry_btn = QtWidgets.QPushButton("🔄 Ask Agent to Fix")
        self.retry_btn.setObjectName("RetryBtn")
        self.retry_btn.setToolTip("Send the error back to the agent to fix")
        self.retry_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.retry_btn.hide()

        btn_layout.addStretch()
        btn_layout.addWidget(self.retry_btn)
        btn_layout.addWidget(self.approve_btn)
        btn_layout.addWidget(self.reject_btn)

        review_layout.addWidget(self.review_label)
        review_layout.addWidget(self.review_code)
        review_layout.addLayout(btn_layout)
        self.review_panel.hide()

        chat_layout.addLayout(top_bar)
        chat_layout.addWidget(self.chat_display, stretch=1)
        chat_layout.addWidget(self.cmd_popup)
        chat_layout.addLayout(ctx_bar)
        chat_layout.addWidget(self.review_panel)
        chat_layout.addWidget(self.warning_label)
        chat_layout.addWidget(input_container)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.chat_area)
        splitter.setSizes([250, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)
