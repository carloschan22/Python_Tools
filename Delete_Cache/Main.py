import sys
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QMessageBox
)
import shutil

class FileDeleter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Carlos_Chan-CacheDeleteTool-V1.1  2024-11-1")
        self.resize(415, 200)

        self.layout = QVBoxLayout(self)

        # file path selection section
        self.path_layout = QHBoxLayout()
        self.path_label = QLabel("FilePath:")
        self.path_input = QLineEdit()
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_folder)

        self.path_layout.addWidget(self.path_label)
        self.path_layout.addWidget(self.path_input)
        self.path_layout.addWidget(self.browse_button)
        self.layout.addLayout(self.path_layout)

        # layout for storing the file name input box
        self.file_inputs_layout = QVBoxLayout()
        self.layout.addLayout(self.file_inputs_layout)

        # by default two file name input fields are added which are pre filled respectively ".pytest_cache" and "__pycache__"
        self.file_name_inputs = []
        self.add_file_name_input(".pytest_cache")
        self.add_file_name_input("__pycache__")
        self.add_file_name_input("mp4")
        self.add_file_name_input("jpg")

        # plus button
        self.add_button = QPushButton("Add files to be deleted")
        self.add_button.clicked.connect(self.add_file_name_input)
        self.layout.addWidget(self.add_button)

        # delete file button
        self.delete_button = QPushButton("DeleteFile")
        self.delete_button.clicked.connect(self.delete_files)
        self.layout.addWidget(self.delete_button)

    def add_file_name_input(self, default_text=""):
        file_name_input = QLineEdit()
        file_name_input.setPlaceholderText("Please enter a file name or extension.")
        
        if isinstance(default_text, str):
            file_name_input.setText(default_text)  # set default file name
        
        self.file_name_inputs.append(file_name_input)

        # add a new input box to the file name input layout
        self.file_inputs_layout.addWidget(file_name_input)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            self.path_input.setText(folder)

    def delete_files(self):
        folder_path = self.path_input.text()
        if not os.path.exists(folder_path):
            QMessageBox.warning(self, "Error!!!", "The specified file path does not exist")
            return

        # get the input file name or extension and uniformly convert to lowercase
        file_names = [file_input.text().strip().lower() for file_input in self.file_name_inputs if file_input.text().strip()]

        if not file_names:
            QMessageBox.warning(self, "Error!!!", "Please enter at least one file name or extension")
            return

        deleted_files = []
        failed_deletions = []

        # traversing a directory and all its subdirectories
        for root, dirs, files in os.walk(folder_path):
            for file_name in file_names:
                # delete a folder or specific file name
                file_path = os.path.join(root, file_name)
                if os.path.exists(file_path):
                    try:
                        shutil.rmtree(file_path)
                        deleted_files.append(file_path)
                    except Exception as e:
                        failed_deletions.append((file_path, str(e)))

                # if you enter an extension delete files of the corresponding type
                for file in files:
                    # Determine whether it is a file with a matching extension (ignoring case)
                    if file.lower().endswith(f".{file_name}"):
                        full_file_path = os.path.join(root, file)
                        try:
                            os.remove(full_file_path)
                            deleted_files.append(full_file_path)
                        except Exception as e:
                            failed_deletions.append((full_file_path, str(e)))

        # prompt for successfully deleted files
        if deleted_files:
            QMessageBox.information(self, "Success", f"The following files have been deleted:\n" + "\n".join(deleted_files))

        # prompt for file deletion failure and reason
        if failed_deletions:
            error_message = "\n".join([f"{path}: {reason}" for path, reason in failed_deletions])
            QMessageBox.warning(self, "Partial deletion failed", f"The following files failed to be deleted:\n{error_message}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = FileDeleter()
    window.show()

    sys.exit(app.exec())
