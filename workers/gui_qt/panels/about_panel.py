"""
About Panel for frankentrack GUI.

Displays information about the application, author, and third-party packages.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap

from config.config import APP_NAME, APP_VERSION


class AboutPanel(QWidget):
    """About panel showing application information and credits."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Build the about panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # App title and version
        title_frame = QFrame()
        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(8, 8, 8, 8)
        
        title_label = QLabel(f"{APP_NAME}")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title_label)
        
        version_label = QLabel(f"Version {APP_VERSION}")
        version_font = QFont()
        version_font.setPointSize(12)
        version_label.setFont(version_font)
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setProperty("status", "info")
        title_layout.addWidget(version_label)
        
        # Add logo image
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        try:
            import os
            # Find the logo file relative to this module
            current_dir = os.path.dirname(__file__)
            logo_path = os.path.join(current_dir, '..', '..', '..', 'img', 'frankentrack_logo.png')
            logo_path = os.path.normpath(logo_path)
            
            if os.path.exists(logo_path):
                pixmap = QPixmap(logo_path)
                if not pixmap.isNull():
                    # Scale logo to reasonable size (max 200px width, maintain aspect ratio)
                    scaled_pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    logo_label.setPixmap(scaled_pixmap)
                else:
                    logo_label.setText("Logo not found")
            else:
                logo_label.setText("Logo not found")
        except Exception as e:
            logo_label.setText("Logo load error")
        
        title_layout.addWidget(logo_label)
        
        layout.addWidget(title_frame)
        
        # Description
        desc_label = QLabel("Real-time head tracking solution using IMU sensors and computer vision")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Author and GitHub info
        author_frame = QFrame()
        author_frame.setFrameStyle(QFrame.Panel | QFrame.Raised)
        author_layout = QVBoxLayout(author_frame)
        author_layout.setContentsMargins(12, 12, 12, 12)
        
        author_title = QLabel("Author & Source")
        author_font = QFont()
        author_font.setPointSize(12)
        author_font.setBold(True)
        author_title.setFont(author_font)
        author_layout.addWidget(author_title)
        
        author_label = QLabel("Created by: anmagx")
        author_layout.addWidget(author_label)
        
        github_label = QLabel('<a href="https://github.com/anmagx/frankentrack" style="color: #4CAF50; text-decoration: none;">GitHub Repository: github.com/anmagx/frankentrack</a>')
        github_label.setOpenExternalLinks(True)
        github_label.setTextFormat(Qt.RichText)
        github_label.setProperty("status", "info")  # Use theme info color for link
        author_layout.addWidget(github_label)
        
        layout.addWidget(author_frame)
        
        # Third-party packages
        packages_frame = QFrame()
        packages_frame.setFrameStyle(QFrame.Panel | QFrame.Raised)
        packages_layout = QVBoxLayout(packages_frame)
        packages_layout.setContentsMargins(12, 12, 12, 12)
        
        packages_title = QLabel("Third-Party Packages")
        packages_font = QFont()
        packages_font.setPointSize(12)
        packages_font.setBold(True)
        packages_title.setFont(packages_font)
        packages_layout.addWidget(packages_title)
        
        # Package list in a text area
        packages_text = QTextEdit()
        packages_text.setReadOnly(True)
        packages_text.setMaximumHeight(200)
        
        packages_content = """• PyQt5 - Cross-platform GUI toolkit
• NumPy - Numerical computing library
• OpenCV (cv2) - Computer vision library
• pseyepy - PS3 Eye camera support
• keyboard - Global hotkey support
• pygame - gamepad hotkey support for Python
• Pillow (PIL) - Image processing
• pyserial - Serial communication
• h5py - HDF5 file format support

This application uses these excellent open-source libraries 
to provide comprehensive head tracking functionality."""
        
        packages_text.setPlainText(packages_content)
        packages_layout.addWidget(packages_text)
        
        layout.addWidget(packages_frame)
        
        # Add stretch to push content to top
        layout.addStretch()