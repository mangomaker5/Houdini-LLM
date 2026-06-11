# CSS styles for the Houdini AI Agent UI

# Main application stylesheet
GLOBAL_STYLE = """
    QWidget {
        background-color: #333333;
        color: #dfdfdf;
        font-family: "Segoe UI", "Helvetica Neue", Helvetica, sans-serif;
        font-size: 14px;
    }
    QToolTip {
        color: #dfdfdf;
        background-color: #2b2b2b;
        border: 1px solid #f1c40f;
        padding: 5px;
        font-size: 13px;
        font-weight: bold;
    }
    QTextBrowser {
        background-color: #333333;
        border: none;
    }
    #InputContainer {
        background-color: #2b2b2b;
        border: 1px solid #444444;
        border-radius: 12px;
    }
    #InputTextEdit {
        background-color: transparent;
        border: none;
        color: #dfdfdf;
        padding: 10px;
        font-size: 14px;
    }
    #SendButton {
        background-color: #19c37d;
        color: white;
        font-size: 16px;
        font-weight: bold;
        border-radius: 6px;
        border: none;
        padding: 5px;
        margin-right: 5px;
        margin-bottom: 5px;
    }
    #SendButton:hover {
        background-color: #1a8f5f;
    }
    #ExecuteButton {
        background-color: #ab68ff;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 12px;
        font-weight: bold;
    }
    #ExecuteButton:hover {
        background-color: #9245f3;
    }
    #SettingsButton {
        background-color: transparent;
        color: #aaaaaa;
        font-size: 14px;
        font-weight: bold;
        border: 1px solid #444444;
        border-radius: 6px;
        padding: 5px 10px;
    }
    #SettingsButton:hover {
        background-color: #444444;
        color: white;
    }
    QComboBox {
        background-color: #2b2b2b;
        border: 1px solid #444444;
        border-radius: 6px;
        color: #dfdfdf;
        font-weight: bold;
        font-size: 14px;
        padding: 5px 10px;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 25px;
        border-left: 1px solid #444444;
    }
    QComboBox::down-arrow {
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid #dfdfdf;
        margin-right: 8px;
    }
    QScrollBar:vertical {
        border: none;
        background: #333333;
        width: 8px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #555555;
        min-height: 20px;
        border-radius: 4px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
    }
    
    /* Sidebar specific */
    #Sidebar {
        background-color: #2b2b2b;
        border-right: 1px solid #444444;
    }
    #SessionScroll {
        background-color: transparent;
        border: none;
    }
    #SessionContainer {
        background-color: transparent;
    }
    #NewChatButton {
        background-color: transparent;
        border: 1px solid #555555;
        color: #dfdfdf;
        border-radius: 6px;
        padding: 10px;
        margin: 10px;
        font-weight: bold;
        font-size: 14px;
        text-align: left;
    }
    #NewChatButton:hover {
        background-color: #444444;
    }
    
    /* Splitter Handle / Slider styling */
    QSplitter::handle {
        background-color: #444444;
        width: 3px;
        margin: 0px;
    }
    QSplitter::handle:hover {
        background-color: #ab68ff;
    }
    QSplitter::handle:pressed {
        background-color: #9245f3;
    }
    
    /* Session Window UI styling */
    QProgressBar#ContextProgressBar {
        border: 1px solid #444444;
        border-radius: 4px;
        background-color: #2b2b2b;
        text-align: center;
        color: #dfdfdf;
        font-size: 10px;
        height: 12px;
    }
    QProgressBar#ContextProgressBar::chunk {
        background-color: #19c37d;
        border-radius: 3px;
    }
    QProgressBar#ContextProgressBar[warning="true"]::chunk {
        background-color: #f59e0b;
    }
    QProgressBar#ContextProgressBar[danger="true"]::chunk {
        background-color: #ef4444;
    }
    
    QLabel#WarningLabel {
        color: #f59e0b;
        background-color: #3f2a14;
        border: 1px solid #f59e0b;
        border-radius: 4px;
        padding: 6px;
        font-size: 12px;
        font-weight: bold;
    }
    
    /* Session Item Widget styling */
    QWidget#SessionItemWidget {
        background-color: transparent;
        border-radius: 6px;
    }
    QWidget#SessionItemWidget:hover {
        background-color: #444444;
    }
    QWidget#SessionItemWidget[active="true"] {
        background-color: #555555;
    }
    QLabel#SessionTitleLabel {
        color: #dfdfdf;
        font-size: 14px;
        background: transparent;
        border: none;
    }
    QWidget#SessionItemWidget[active="true"] QLabel#SessionTitleLabel {
        font-weight: bold;
    }
    QPushButton#SessionEditBtn, QPushButton#SessionDeleteBtn {
        background-color: #2b2b2b;
        border: 1px solid #444444;
        color: #dfdfdf;
        font-size: 11px;
        padding: 4px 8px;
        border-radius: 4px;
    }
    QPushButton#SessionEditBtn:hover {
        background-color: #444444;
        color: white;
    }
    QPushButton#SessionDeleteBtn:hover {
        background-color: #ef4444;
        color: white;
        border-color: #ef4444;
    }
    
    /* Command Autocomplete Popup */
    QListWidget#CommandPopup {
        background-color: #2b2b2b;
        border: 1px solid #555555;
        border-radius: 4px;
        color: #dfdfdf;
        font-size: 13px;
        outline: none;
    }
    QListWidget#CommandPopup::item {
        padding: 4px;
    }
    QListWidget#CommandPopup::item:hover {
        background-color: #444444;
    }
"""
