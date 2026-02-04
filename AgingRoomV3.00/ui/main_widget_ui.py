# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_widget.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenuBar, QPushButton, QSizePolicy,
    QSpacerItem, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

class Ui_MainWidget(object):
    def setupUi(self, MainWidget):
        if not MainWidget.objectName():
            MainWidget.setObjectName(u"MainWidget")
        MainWidget.setMinimumSize(QSize(1400, 800))
        self.action_home = QAction(MainWidget)
        self.action_home.setObjectName(u"action_home")
        self.action_history = QAction(MainWidget)
        self.action_history.setObjectName(u"action_history")
        self.action_about = QAction(MainWidget)
        self.action_about.setObjectName(u"action_about")
        self.mainLayout = QVBoxLayout(MainWidget)
        self.mainLayout.setObjectName(u"mainLayout")
        self.menuBar = QMenuBar(MainWidget)
        self.menuBar.setObjectName(u"menuBar")
        self.menuBar.setNativeMenuBar(False)

        self.mainLayout.addWidget(self.menuBar)

        self.stackedPages = QStackedWidget(MainWidget)
        self.stackedPages.setObjectName(u"stackedPages")
        self.page_home = QWidget()
        self.page_home.setObjectName(u"page_home")
        self.homeLayout = QVBoxLayout(self.page_home)
        self.homeLayout.setObjectName(u"homeLayout")
        self.groupBox_1 = QGroupBox(self.page_home)
        self.groupBox_1.setObjectName(u"groupBox_1")
        self.groupLayout_1 = QHBoxLayout(self.groupBox_1)
        self.groupLayout_1.setObjectName(u"groupLayout_1")
        self.iconFrame_1 = QFrame(self.groupBox_1)
        self.iconFrame_1.setObjectName(u"iconFrame_1")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.iconFrame_1.sizePolicy().hasHeightForWidth())
        self.iconFrame_1.setSizePolicy(sizePolicy)
        self.iconFrame_1.setFrameShape(QFrame.StyledPanel)
        self.iconLayout_1 = QVBoxLayout(self.iconFrame_1)
        self.iconLayout_1.setObjectName(u"iconLayout_1")
        self.iconTable_1 = QTableWidget(self.iconFrame_1)
        self.iconTable_1.setObjectName(u"iconTable_1")
        sizePolicy.setHeightForWidth(self.iconTable_1.sizePolicy().hasHeightForWidth())
        self.iconTable_1.setSizePolicy(sizePolicy)
        self.iconTable_1.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iconTable_1.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iconTable_1.setRowCount(4)
        self.iconTable_1.setColumnCount(25)

        self.iconLayout_1.addWidget(self.iconTable_1)


        self.groupLayout_1.addWidget(self.iconFrame_1)

        self.controlFrame_1 = QFrame(self.groupBox_1)
        self.controlFrame_1.setObjectName(u"controlFrame_1")
        self.controlFrame_1.setMinimumSize(QSize(360, 0))
        self.controlFrame_1.setMaximumSize(QSize(360, 16777215))
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.controlFrame_1.sizePolicy().hasHeightForWidth())
        self.controlFrame_1.setSizePolicy(sizePolicy1)
        self.controlFrame_1.setFrameShape(QFrame.StyledPanel)
        self.controlLayout_1 = QGridLayout(self.controlFrame_1)
        self.controlLayout_1.setObjectName(u"controlLayout_1")
        self.controlLayout_1.setHorizontalSpacing(6)
        self.controlLayout_1.setVerticalSpacing(6)
        self.lbl_runtime_1 = QLabel(self.controlFrame_1)
        self.lbl_runtime_1.setObjectName(u"lbl_runtime_1")

        self.controlLayout_1.addWidget(self.lbl_runtime_1, 0, 2, 1, 1)

        self.edit_runtime_1 = QLineEdit(self.controlFrame_1)
        self.edit_runtime_1.setObjectName(u"edit_runtime_1")
        self.edit_runtime_1.setReadOnly(True)

        self.controlLayout_1.addWidget(self.edit_runtime_1, 0, 3, 1, 1)

        self.lbl_remaining_1 = QLabel(self.controlFrame_1)
        self.lbl_remaining_1.setObjectName(u"lbl_remaining_1")

        self.controlLayout_1.addWidget(self.lbl_remaining_1, 1, 2, 1, 1)

        self.edit_remaining_1 = QLineEdit(self.controlFrame_1)
        self.edit_remaining_1.setObjectName(u"edit_remaining_1")
        self.edit_remaining_1.setReadOnly(True)

        self.controlLayout_1.addWidget(self.edit_remaining_1, 1, 3, 1, 1)

        self.lbl_product_1 = QLabel(self.controlFrame_1)
        self.lbl_product_1.setObjectName(u"lbl_product_1")

        self.controlLayout_1.addWidget(self.lbl_product_1, 0, 0, 1, 1)

        self.combo_product_1 = QComboBox(self.controlFrame_1)
        self.combo_product_1.setObjectName(u"combo_product_1")

        self.controlLayout_1.addWidget(self.combo_product_1, 0, 1, 1, 1)

        self.lbl_aging_time_1 = QLabel(self.controlFrame_1)
        self.lbl_aging_time_1.setObjectName(u"lbl_aging_time_1")

        self.controlLayout_1.addWidget(self.lbl_aging_time_1, 1, 0, 1, 1)

        self.combo_aging_time_1 = QComboBox(self.controlFrame_1)
        self.combo_aging_time_1.setObjectName(u"combo_aging_time_1")

        self.controlLayout_1.addWidget(self.combo_aging_time_1, 1, 1, 1, 1)

        self.lbl_qty_1 = QLabel(self.controlFrame_1)
        self.lbl_qty_1.setObjectName(u"lbl_qty_1")

        self.controlLayout_1.addWidget(self.lbl_qty_1, 2, 0, 1, 1)

        self.edit_qty_1 = QLabel(self.controlFrame_1)
        self.edit_qty_1.setObjectName(u"edit_qty_1")

        self.controlLayout_1.addWidget(self.edit_qty_1, 2, 1, 1, 1)

        self.lbl_good_1 = QLabel(self.controlFrame_1)
        self.lbl_good_1.setObjectName(u"lbl_good_1")

        self.controlLayout_1.addWidget(self.lbl_good_1, 3, 0, 1, 1)

        self.edit_good_1 = QLabel(self.controlFrame_1)
        self.edit_good_1.setObjectName(u"edit_good_1")

        self.controlLayout_1.addWidget(self.edit_good_1, 3, 1, 1, 1)

        self.lbl_bad_1 = QLabel(self.controlFrame_1)
        self.lbl_bad_1.setObjectName(u"lbl_bad_1")

        self.controlLayout_1.addWidget(self.lbl_bad_1, 4, 0, 1, 1)

        self.edit_bad_1 = QLabel(self.controlFrame_1)
        self.edit_bad_1.setObjectName(u"edit_bad_1")

        self.controlLayout_1.addWidget(self.edit_bad_1, 4, 1, 1, 1)

        self.lbl_pass_rate_1 = QLabel(self.controlFrame_1)
        self.lbl_pass_rate_1.setObjectName(u"lbl_pass_rate_1")

        self.controlLayout_1.addWidget(self.lbl_pass_rate_1, 5, 0, 1, 1)

        self.text_pass_rate_1 = QLabel(self.controlFrame_1)
        self.text_pass_rate_1.setObjectName(u"text_pass_rate_1")

        self.controlLayout_1.addWidget(self.text_pass_rate_1, 5, 1, 1, 1)

        self.lbl_fail_rate_1 = QLabel(self.controlFrame_1)
        self.lbl_fail_rate_1.setObjectName(u"lbl_fail_rate_1")

        self.controlLayout_1.addWidget(self.lbl_fail_rate_1, 6, 0, 1, 1)

        self.text_fail_rate_1 = QLabel(self.controlFrame_1)
        self.text_fail_rate_1.setObjectName(u"text_fail_rate_1")

        self.controlLayout_1.addWidget(self.text_fail_rate_1, 6, 1, 1, 1)

        self.lbl_temp_1 = QLabel(self.controlFrame_1)
        self.lbl_temp_1.setObjectName(u"lbl_temp_1")

        self.controlLayout_1.addWidget(self.lbl_temp_1, 2, 2, 1, 1)

        self.text_temp_1 = QLabel(self.controlFrame_1)
        self.text_temp_1.setObjectName(u"text_temp_1")

        self.controlLayout_1.addWidget(self.text_temp_1, 2, 3, 1, 1)

        self.lbl_worker_1 = QLabel(self.controlFrame_1)
        self.lbl_worker_1.setObjectName(u"lbl_worker_1")

        self.controlLayout_1.addWidget(self.lbl_worker_1, 3, 2, 1, 1)

        self.combo_worker_1 = QComboBox(self.controlFrame_1)
        self.combo_worker_1.setObjectName(u"combo_worker_1")

        self.controlLayout_1.addWidget(self.combo_worker_1, 3, 3, 1, 1)

        self.lbl_start_time_1 = QLabel(self.controlFrame_1)
        self.lbl_start_time_1.setObjectName(u"lbl_start_time_1")

        self.controlLayout_1.addWidget(self.lbl_start_time_1, 4, 2, 1, 1)

        self.text_start_time_1 = QLabel(self.controlFrame_1)
        self.text_start_time_1.setObjectName(u"text_start_time_1")

        self.controlLayout_1.addWidget(self.text_start_time_1, 4, 3, 1, 1)

        self.lbl_end_time_1 = QLabel(self.controlFrame_1)
        self.lbl_end_time_1.setObjectName(u"lbl_end_time_1")

        self.controlLayout_1.addWidget(self.lbl_end_time_1, 5, 2, 1, 1)

        self.text_end_time_1 = QLabel(self.controlFrame_1)
        self.text_end_time_1.setObjectName(u"text_end_time_1")

        self.controlLayout_1.addWidget(self.text_end_time_1, 5, 3, 1, 1)

        self.btn_start_1 = QPushButton(self.controlFrame_1)
        self.btn_start_1.setObjectName(u"btn_start_1")

        self.controlLayout_1.addWidget(self.btn_start_1, 6, 2, 1, 1)

        self.btn_pause_1 = QPushButton(self.controlFrame_1)
        self.btn_pause_1.setObjectName(u"btn_pause_1")
        self.btn_pause_1.setEnabled(False)

        self.controlLayout_1.addWidget(self.btn_pause_1, 6, 3, 1, 1)


        self.groupLayout_1.addWidget(self.controlFrame_1)


        self.homeLayout.addWidget(self.groupBox_1)

        self.groupBox_2 = QGroupBox(self.page_home)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.groupLayout_2 = QHBoxLayout(self.groupBox_2)
        self.groupLayout_2.setObjectName(u"groupLayout_2")
        self.iconFrame_2 = QFrame(self.groupBox_2)
        self.iconFrame_2.setObjectName(u"iconFrame_2")
        sizePolicy.setHeightForWidth(self.iconFrame_2.sizePolicy().hasHeightForWidth())
        self.iconFrame_2.setSizePolicy(sizePolicy)
        self.iconFrame_2.setFrameShape(QFrame.StyledPanel)
        self.iconLayout_2 = QVBoxLayout(self.iconFrame_2)
        self.iconLayout_2.setObjectName(u"iconLayout_2")
        self.iconTable_2 = QTableWidget(self.iconFrame_2)
        self.iconTable_2.setObjectName(u"iconTable_2")
        sizePolicy.setHeightForWidth(self.iconTable_2.sizePolicy().hasHeightForWidth())
        self.iconTable_2.setSizePolicy(sizePolicy)
        self.iconTable_2.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iconTable_2.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iconTable_2.setRowCount(4)
        self.iconTable_2.setColumnCount(25)

        self.iconLayout_2.addWidget(self.iconTable_2)


        self.groupLayout_2.addWidget(self.iconFrame_2)

        self.controlFrame_2 = QFrame(self.groupBox_2)
        self.controlFrame_2.setObjectName(u"controlFrame_2")
        self.controlFrame_2.setMinimumSize(QSize(360, 0))
        self.controlFrame_2.setMaximumSize(QSize(360, 16777215))
        sizePolicy1.setHeightForWidth(self.controlFrame_2.sizePolicy().hasHeightForWidth())
        self.controlFrame_2.setSizePolicy(sizePolicy1)
        self.controlFrame_2.setFrameShape(QFrame.StyledPanel)
        self.controlLayout_2 = QGridLayout(self.controlFrame_2)
        self.controlLayout_2.setObjectName(u"controlLayout_2")
        self.controlLayout_2.setHorizontalSpacing(6)
        self.controlLayout_2.setVerticalSpacing(6)
        self.lbl_runtime_2 = QLabel(self.controlFrame_2)
        self.lbl_runtime_2.setObjectName(u"lbl_runtime_2")

        self.controlLayout_2.addWidget(self.lbl_runtime_2, 0, 2, 1, 1)

        self.edit_runtime_2 = QLineEdit(self.controlFrame_2)
        self.edit_runtime_2.setObjectName(u"edit_runtime_2")
        self.edit_runtime_2.setReadOnly(True)

        self.controlLayout_2.addWidget(self.edit_runtime_2, 0, 3, 1, 1)

        self.lbl_remaining_2 = QLabel(self.controlFrame_2)
        self.lbl_remaining_2.setObjectName(u"lbl_remaining_2")

        self.controlLayout_2.addWidget(self.lbl_remaining_2, 1, 2, 1, 1)

        self.edit_remaining_2 = QLineEdit(self.controlFrame_2)
        self.edit_remaining_2.setObjectName(u"edit_remaining_2")
        self.edit_remaining_2.setReadOnly(True)

        self.controlLayout_2.addWidget(self.edit_remaining_2, 1, 3, 1, 1)

        self.lbl_product_2 = QLabel(self.controlFrame_2)
        self.lbl_product_2.setObjectName(u"lbl_product_2")

        self.controlLayout_2.addWidget(self.lbl_product_2, 0, 0, 1, 1)

        self.combo_product_2 = QComboBox(self.controlFrame_2)
        self.combo_product_2.setObjectName(u"combo_product_2")

        self.controlLayout_2.addWidget(self.combo_product_2, 0, 1, 1, 1)

        self.lbl_aging_time_2 = QLabel(self.controlFrame_2)
        self.lbl_aging_time_2.setObjectName(u"lbl_aging_time_2")

        self.controlLayout_2.addWidget(self.lbl_aging_time_2, 1, 0, 1, 1)

        self.combo_aging_time_2 = QComboBox(self.controlFrame_2)
        self.combo_aging_time_2.setObjectName(u"combo_aging_time_2")

        self.controlLayout_2.addWidget(self.combo_aging_time_2, 1, 1, 1, 1)

        self.lbl_qty_2 = QLabel(self.controlFrame_2)
        self.lbl_qty_2.setObjectName(u"lbl_qty_2")

        self.controlLayout_2.addWidget(self.lbl_qty_2, 2, 0, 1, 1)

        self.edit_qty_2 = QLabel(self.controlFrame_2)
        self.edit_qty_2.setObjectName(u"edit_qty_2")

        self.controlLayout_2.addWidget(self.edit_qty_2, 2, 1, 1, 1)

        self.lbl_good_2 = QLabel(self.controlFrame_2)
        self.lbl_good_2.setObjectName(u"lbl_good_2")

        self.controlLayout_2.addWidget(self.lbl_good_2, 3, 0, 1, 1)

        self.edit_good_2 = QLabel(self.controlFrame_2)
        self.edit_good_2.setObjectName(u"edit_good_2")

        self.controlLayout_2.addWidget(self.edit_good_2, 3, 1, 1, 1)

        self.lbl_bad_2 = QLabel(self.controlFrame_2)
        self.lbl_bad_2.setObjectName(u"lbl_bad_2")

        self.controlLayout_2.addWidget(self.lbl_bad_2, 4, 0, 1, 1)

        self.edit_bad_2 = QLabel(self.controlFrame_2)
        self.edit_bad_2.setObjectName(u"edit_bad_2")

        self.controlLayout_2.addWidget(self.edit_bad_2, 4, 1, 1, 1)

        self.lbl_pass_rate_2 = QLabel(self.controlFrame_2)
        self.lbl_pass_rate_2.setObjectName(u"lbl_pass_rate_2")

        self.controlLayout_2.addWidget(self.lbl_pass_rate_2, 5, 0, 1, 1)

        self.text_pass_rate_2 = QLabel(self.controlFrame_2)
        self.text_pass_rate_2.setObjectName(u"text_pass_rate_2")

        self.controlLayout_2.addWidget(self.text_pass_rate_2, 5, 1, 1, 1)

        self.lbl_fail_rate_2 = QLabel(self.controlFrame_2)
        self.lbl_fail_rate_2.setObjectName(u"lbl_fail_rate_2")

        self.controlLayout_2.addWidget(self.lbl_fail_rate_2, 6, 0, 1, 1)

        self.text_fail_rate_2 = QLabel(self.controlFrame_2)
        self.text_fail_rate_2.setObjectName(u"text_fail_rate_2")

        self.controlLayout_2.addWidget(self.text_fail_rate_2, 6, 1, 1, 1)

        self.lbl_temp_2 = QLabel(self.controlFrame_2)
        self.lbl_temp_2.setObjectName(u"lbl_temp_2")

        self.controlLayout_2.addWidget(self.lbl_temp_2, 2, 2, 1, 1)

        self.text_temp_2 = QLabel(self.controlFrame_2)
        self.text_temp_2.setObjectName(u"text_temp_2")

        self.controlLayout_2.addWidget(self.text_temp_2, 2, 3, 1, 1)

        self.lbl_worker_2 = QLabel(self.controlFrame_2)
        self.lbl_worker_2.setObjectName(u"lbl_worker_2")

        self.controlLayout_2.addWidget(self.lbl_worker_2, 3, 2, 1, 1)

        self.combo_worker_2 = QComboBox(self.controlFrame_2)
        self.combo_worker_2.setObjectName(u"combo_worker_2")

        self.controlLayout_2.addWidget(self.combo_worker_2, 3, 3, 1, 1)

        self.lbl_start_time_2 = QLabel(self.controlFrame_2)
        self.lbl_start_time_2.setObjectName(u"lbl_start_time_2")

        self.controlLayout_2.addWidget(self.lbl_start_time_2, 4, 2, 1, 1)

        self.text_start_time_2 = QLabel(self.controlFrame_2)
        self.text_start_time_2.setObjectName(u"text_start_time_2")

        self.controlLayout_2.addWidget(self.text_start_time_2, 4, 3, 1, 1)

        self.lbl_end_time_2 = QLabel(self.controlFrame_2)
        self.lbl_end_time_2.setObjectName(u"lbl_end_time_2")

        self.controlLayout_2.addWidget(self.lbl_end_time_2, 5, 2, 1, 1)

        self.text_end_time_2 = QLabel(self.controlFrame_2)
        self.text_end_time_2.setObjectName(u"text_end_time_2")

        self.controlLayout_2.addWidget(self.text_end_time_2, 5, 3, 1, 1)

        self.btn_start_2 = QPushButton(self.controlFrame_2)
        self.btn_start_2.setObjectName(u"btn_start_2")

        self.controlLayout_2.addWidget(self.btn_start_2, 6, 2, 1, 1)

        self.btn_pause_2 = QPushButton(self.controlFrame_2)
        self.btn_pause_2.setObjectName(u"btn_pause_2")
        self.btn_pause_2.setEnabled(False)

        self.controlLayout_2.addWidget(self.btn_pause_2, 6, 3, 1, 1)


        self.groupLayout_2.addWidget(self.controlFrame_2)


        self.homeLayout.addWidget(self.groupBox_2)

        self.groupBox_3 = QGroupBox(self.page_home)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.groupLayout_3 = QHBoxLayout(self.groupBox_3)
        self.groupLayout_3.setObjectName(u"groupLayout_3")
        self.iconFrame_3 = QFrame(self.groupBox_3)
        self.iconFrame_3.setObjectName(u"iconFrame_3")
        sizePolicy.setHeightForWidth(self.iconFrame_3.sizePolicy().hasHeightForWidth())
        self.iconFrame_3.setSizePolicy(sizePolicy)
        self.iconFrame_3.setFrameShape(QFrame.StyledPanel)
        self.iconLayout_3 = QVBoxLayout(self.iconFrame_3)
        self.iconLayout_3.setObjectName(u"iconLayout_3")
        self.iconTable_3 = QTableWidget(self.iconFrame_3)
        self.iconTable_3.setObjectName(u"iconTable_3")
        sizePolicy.setHeightForWidth(self.iconTable_3.sizePolicy().hasHeightForWidth())
        self.iconTable_3.setSizePolicy(sizePolicy)
        self.iconTable_3.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iconTable_3.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iconTable_3.setRowCount(4)
        self.iconTable_3.setColumnCount(25)

        self.iconLayout_3.addWidget(self.iconTable_3)


        self.groupLayout_3.addWidget(self.iconFrame_3)

        self.controlFrame_3 = QFrame(self.groupBox_3)
        self.controlFrame_3.setObjectName(u"controlFrame_3")
        self.controlFrame_3.setMinimumSize(QSize(360, 0))
        self.controlFrame_3.setMaximumSize(QSize(360, 16777215))
        sizePolicy1.setHeightForWidth(self.controlFrame_3.sizePolicy().hasHeightForWidth())
        self.controlFrame_3.setSizePolicy(sizePolicy1)
        self.controlFrame_3.setFrameShape(QFrame.StyledPanel)
        self.controlLayout_3 = QGridLayout(self.controlFrame_3)
        self.controlLayout_3.setObjectName(u"controlLayout_3")
        self.controlLayout_3.setHorizontalSpacing(6)
        self.controlLayout_3.setVerticalSpacing(6)
        self.lbl_runtime_3 = QLabel(self.controlFrame_3)
        self.lbl_runtime_3.setObjectName(u"lbl_runtime_3")

        self.controlLayout_3.addWidget(self.lbl_runtime_3, 0, 2, 1, 1)

        self.edit_runtime_3 = QLineEdit(self.controlFrame_3)
        self.edit_runtime_3.setObjectName(u"edit_runtime_3")
        self.edit_runtime_3.setReadOnly(True)

        self.controlLayout_3.addWidget(self.edit_runtime_3, 0, 3, 1, 1)

        self.lbl_remaining_3 = QLabel(self.controlFrame_3)
        self.lbl_remaining_3.setObjectName(u"lbl_remaining_3")

        self.controlLayout_3.addWidget(self.lbl_remaining_3, 1, 2, 1, 1)

        self.edit_remaining_3 = QLineEdit(self.controlFrame_3)
        self.edit_remaining_3.setObjectName(u"edit_remaining_3")
        self.edit_remaining_3.setReadOnly(True)

        self.controlLayout_3.addWidget(self.edit_remaining_3, 1, 3, 1, 1)

        self.lbl_product_3 = QLabel(self.controlFrame_3)
        self.lbl_product_3.setObjectName(u"lbl_product_3")

        self.controlLayout_3.addWidget(self.lbl_product_3, 0, 0, 1, 1)

        self.combo_product_3 = QComboBox(self.controlFrame_3)
        self.combo_product_3.setObjectName(u"combo_product_3")

        self.controlLayout_3.addWidget(self.combo_product_3, 0, 1, 1, 1)

        self.lbl_aging_time_3 = QLabel(self.controlFrame_3)
        self.lbl_aging_time_3.setObjectName(u"lbl_aging_time_3")

        self.controlLayout_3.addWidget(self.lbl_aging_time_3, 1, 0, 1, 1)

        self.combo_aging_time_3 = QComboBox(self.controlFrame_3)
        self.combo_aging_time_3.setObjectName(u"combo_aging_time_3")

        self.controlLayout_3.addWidget(self.combo_aging_time_3, 1, 1, 1, 1)

        self.lbl_qty_3 = QLabel(self.controlFrame_3)
        self.lbl_qty_3.setObjectName(u"lbl_qty_3")

        self.controlLayout_3.addWidget(self.lbl_qty_3, 2, 0, 1, 1)

        self.edit_qty_3 = QLabel(self.controlFrame_3)
        self.edit_qty_3.setObjectName(u"edit_qty_3")

        self.controlLayout_3.addWidget(self.edit_qty_3, 2, 1, 1, 1)

        self.lbl_good_3 = QLabel(self.controlFrame_3)
        self.lbl_good_3.setObjectName(u"lbl_good_3")

        self.controlLayout_3.addWidget(self.lbl_good_3, 3, 0, 1, 1)

        self.edit_good_3 = QLabel(self.controlFrame_3)
        self.edit_good_3.setObjectName(u"edit_good_3")

        self.controlLayout_3.addWidget(self.edit_good_3, 3, 1, 1, 1)

        self.lbl_bad_3 = QLabel(self.controlFrame_3)
        self.lbl_bad_3.setObjectName(u"lbl_bad_3")

        self.controlLayout_3.addWidget(self.lbl_bad_3, 4, 0, 1, 1)

        self.edit_bad_3 = QLabel(self.controlFrame_3)
        self.edit_bad_3.setObjectName(u"edit_bad_3")

        self.controlLayout_3.addWidget(self.edit_bad_3, 4, 1, 1, 1)

        self.lbl_pass_rate_3 = QLabel(self.controlFrame_3)
        self.lbl_pass_rate_3.setObjectName(u"lbl_pass_rate_3")

        self.controlLayout_3.addWidget(self.lbl_pass_rate_3, 5, 0, 1, 1)

        self.text_pass_rate_3 = QLabel(self.controlFrame_3)
        self.text_pass_rate_3.setObjectName(u"text_pass_rate_3")

        self.controlLayout_3.addWidget(self.text_pass_rate_3, 5, 1, 1, 1)

        self.lbl_fail_rate_3 = QLabel(self.controlFrame_3)
        self.lbl_fail_rate_3.setObjectName(u"lbl_fail_rate_3")

        self.controlLayout_3.addWidget(self.lbl_fail_rate_3, 6, 0, 1, 1)

        self.text_fail_rate_3 = QLabel(self.controlFrame_3)
        self.text_fail_rate_3.setObjectName(u"text_fail_rate_3")

        self.controlLayout_3.addWidget(self.text_fail_rate_3, 6, 1, 1, 1)

        self.lbl_temp_3 = QLabel(self.controlFrame_3)
        self.lbl_temp_3.setObjectName(u"lbl_temp_3")

        self.controlLayout_3.addWidget(self.lbl_temp_3, 2, 2, 1, 1)

        self.text_temp_3 = QLabel(self.controlFrame_3)
        self.text_temp_3.setObjectName(u"text_temp_3")

        self.controlLayout_3.addWidget(self.text_temp_3, 2, 3, 1, 1)

        self.lbl_worker_3 = QLabel(self.controlFrame_3)
        self.lbl_worker_3.setObjectName(u"lbl_worker_3")

        self.controlLayout_3.addWidget(self.lbl_worker_3, 3, 2, 1, 1)

        self.combo_worker_3 = QComboBox(self.controlFrame_3)
        self.combo_worker_3.setObjectName(u"combo_worker_3")

        self.controlLayout_3.addWidget(self.combo_worker_3, 3, 3, 1, 1)

        self.lbl_start_time_3 = QLabel(self.controlFrame_3)
        self.lbl_start_time_3.setObjectName(u"lbl_start_time_3")

        self.controlLayout_3.addWidget(self.lbl_start_time_3, 4, 2, 1, 1)

        self.text_start_time_3 = QLabel(self.controlFrame_3)
        self.text_start_time_3.setObjectName(u"text_start_time_3")

        self.controlLayout_3.addWidget(self.text_start_time_3, 4, 3, 1, 1)

        self.lbl_end_time_3 = QLabel(self.controlFrame_3)
        self.lbl_end_time_3.setObjectName(u"lbl_end_time_3")

        self.controlLayout_3.addWidget(self.lbl_end_time_3, 5, 2, 1, 1)

        self.text_end_time_3 = QLabel(self.controlFrame_3)
        self.text_end_time_3.setObjectName(u"text_end_time_3")

        self.controlLayout_3.addWidget(self.text_end_time_3, 5, 3, 1, 1)

        self.btn_start_3 = QPushButton(self.controlFrame_3)
        self.btn_start_3.setObjectName(u"btn_start_3")

        self.controlLayout_3.addWidget(self.btn_start_3, 6, 2, 1, 1)

        self.btn_pause_3 = QPushButton(self.controlFrame_3)
        self.btn_pause_3.setObjectName(u"btn_pause_3")
        self.btn_pause_3.setEnabled(False)

        self.controlLayout_3.addWidget(self.btn_pause_3, 6, 3, 1, 1)


        self.groupLayout_3.addWidget(self.controlFrame_3)


        self.homeLayout.addWidget(self.groupBox_3)

        self.stackedPages.addWidget(self.page_home)
        self.page_history = QWidget()
        self.page_history.setObjectName(u"page_history")
        self.historyLayout = QVBoxLayout(self.page_history)
        self.historyLayout.setObjectName(u"historyLayout")
        self.historyControlLayout = QHBoxLayout()
        self.historyControlLayout.setObjectName(u"historyControlLayout")
        self.btn_history_refresh = QPushButton(self.page_history)
        self.btn_history_refresh.setObjectName(u"btn_history_refresh")

        self.historyControlLayout.addWidget(self.btn_history_refresh)

        self.btn_history_export = QPushButton(self.page_history)
        self.btn_history_export.setObjectName(u"btn_history_export")

        self.historyControlLayout.addWidget(self.btn_history_export)

        self.historySpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.historyControlLayout.addItem(self.historySpacer)


        self.historyLayout.addLayout(self.historyControlLayout)

        self.historyFilterLayout = QHBoxLayout()
        self.historyFilterLayout.setObjectName(u"historyFilterLayout")
        self.lbl_history_year = QLabel(self.page_history)
        self.lbl_history_year.setObjectName(u"lbl_history_year")

        self.historyFilterLayout.addWidget(self.lbl_history_year)

        self.combo_history_year = QComboBox(self.page_history)
        self.combo_history_year.setObjectName(u"combo_history_year")

        self.historyFilterLayout.addWidget(self.combo_history_year)

        self.lbl_history_month = QLabel(self.page_history)
        self.lbl_history_month.setObjectName(u"lbl_history_month")

        self.historyFilterLayout.addWidget(self.lbl_history_month)

        self.combo_history_month = QComboBox(self.page_history)
        self.combo_history_month.setObjectName(u"combo_history_month")

        self.historyFilterLayout.addWidget(self.combo_history_month)

        self.lbl_history_day = QLabel(self.page_history)
        self.lbl_history_day.setObjectName(u"lbl_history_day")

        self.historyFilterLayout.addWidget(self.lbl_history_day)

        self.combo_history_day = QComboBox(self.page_history)
        self.combo_history_day.setObjectName(u"combo_history_day")

        self.historyFilterLayout.addWidget(self.combo_history_day)

        self.btn_history_query = QPushButton(self.page_history)
        self.btn_history_query.setObjectName(u"btn_history_query")

        self.historyFilterLayout.addWidget(self.btn_history_query)

        self.historyFilterSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.historyFilterLayout.addItem(self.historyFilterSpacer)


        self.historyLayout.addLayout(self.historyFilterLayout)

        self.historyTable = QTableWidget(self.page_history)
        self.historyTable.setObjectName(u"historyTable")

        self.historyLayout.addWidget(self.historyTable)

        self.stackedPages.addWidget(self.page_history)
        self.page_about = QWidget()
        self.page_about.setObjectName(u"page_about")
        self.aboutLayout = QVBoxLayout(self.page_about)
        self.aboutLayout.setObjectName(u"aboutLayout")
        self.aboutTitle = QLabel(self.page_about)
        self.aboutTitle.setObjectName(u"aboutTitle")
        self.aboutTitle.setAlignment(Qt.AlignCenter)

        self.aboutLayout.addWidget(self.aboutTitle)

        self.aboutVersion = QLabel(self.page_about)
        self.aboutVersion.setObjectName(u"aboutVersion")
        self.aboutVersion.setAlignment(Qt.AlignCenter)

        self.aboutLayout.addWidget(self.aboutVersion)

        self.aboutCopyright = QLabel(self.page_about)
        self.aboutCopyright.setObjectName(u"aboutCopyright")
        self.aboutCopyright.setAlignment(Qt.AlignCenter)

        self.aboutLayout.addWidget(self.aboutCopyright)

        self.aboutWebsite = QLabel(self.page_about)
        self.aboutWebsite.setObjectName(u"aboutWebsite")
        self.aboutWebsite.setAlignment(Qt.AlignCenter)

        self.aboutLayout.addWidget(self.aboutWebsite)

        self.aboutEmail = QLabel(self.page_about)
        self.aboutEmail.setObjectName(u"aboutEmail")
        self.aboutEmail.setAlignment(Qt.AlignCenter)

        self.aboutLayout.addWidget(self.aboutEmail)

        self.aboutSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.aboutLayout.addItem(self.aboutSpacer)

        self.stackedPages.addWidget(self.page_about)

        self.mainLayout.addWidget(self.stackedPages)


        self.menuBar.addAction(self.action_home)
        self.menuBar.addAction(self.action_history)
        self.menuBar.addAction(self.action_about)

        self.retranslateUi(MainWidget)

        self.stackedPages.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWidget)
    # setupUi

    def retranslateUi(self, MainWidget):
        self.action_home.setText(QCoreApplication.translate("MainWidget", u"\u4e3b\u9875", None))
        self.action_history.setText(QCoreApplication.translate("MainWidget", u"\u5386\u53f2", None))
        self.action_about.setText(QCoreApplication.translate("MainWidget", u"\u5173\u4e8e", None))
        self.groupBox_1.setTitle(QCoreApplication.translate("MainWidget", u"\u7b2c1\u7ec4", None))
        self.lbl_runtime_1.setText(QCoreApplication.translate("MainWidget", u"\u8fd0\u884c\u65f6\u95f4\uff1a", None))
        self.lbl_remaining_1.setText(QCoreApplication.translate("MainWidget", u"\u5269\u4f59\u65f6\u95f4\uff1a", None))
        self.lbl_product_1.setText(QCoreApplication.translate("MainWidget", u"\u4ea7\u54c1\u578b\u53f7\uff1a", None))
        self.lbl_aging_time_1.setText(QCoreApplication.translate("MainWidget", u"\u8001\u5316\u65f6\u95f4\uff1a", None))
        self.lbl_qty_1.setText(QCoreApplication.translate("MainWidget", u"\u6570\u91cf\uff1a", None))
        self.edit_qty_1.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_good_1.setText(QCoreApplication.translate("MainWidget", u"\u826f\u54c1\uff1a", None))
        self.edit_good_1.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_bad_1.setText(QCoreApplication.translate("MainWidget", u"\u4e0d\u826f\u54c1\uff1a", None))
        self.edit_bad_1.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_pass_rate_1.setText(QCoreApplication.translate("MainWidget", u"\u5408\u683c\u7387\uff1a", None))
        self.text_pass_rate_1.setText(QCoreApplication.translate("MainWidget", u"0.00%", None))
        self.lbl_fail_rate_1.setText(QCoreApplication.translate("MainWidget", u"\u4e0d\u826f\u7387\uff1a", None))
        self.text_fail_rate_1.setText(QCoreApplication.translate("MainWidget", u"0.00%", None))
        self.lbl_temp_1.setText(QCoreApplication.translate("MainWidget", u"\u5f53\u524d\u6e29\u5ea6\uff1a", None))
        self.text_temp_1.setText(QCoreApplication.translate("MainWidget", u"0\u00b0", None))
        self.lbl_worker_1.setText(QCoreApplication.translate("MainWidget", u"\u64cd\u4f5c\u4eba\u5458\uff1a", None))
        self.lbl_start_time_1.setText(QCoreApplication.translate("MainWidget", u"\u5f00\u59cb\u65f6\u95f4\uff1a", None))
        self.text_start_time_1.setText(QCoreApplication.translate("MainWidget", u"--", None))
        self.lbl_end_time_1.setText(QCoreApplication.translate("MainWidget", u"\u7ed3\u675f\u65f6\u95f4\uff1a", None))
        self.text_end_time_1.setText(QCoreApplication.translate("MainWidget", u"--", None))
        self.btn_start_1.setText(QCoreApplication.translate("MainWidget", u"\u542f\u52a8\u8001\u5316", None))
        self.btn_pause_1.setText(QCoreApplication.translate("MainWidget", u"\u6682\u505c", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("MainWidget", u"\u7b2c2\u7ec4", None))
        self.lbl_runtime_2.setText(QCoreApplication.translate("MainWidget", u"\u8fd0\u884c\u65f6\u95f4\uff1a", None))
        self.lbl_remaining_2.setText(QCoreApplication.translate("MainWidget", u"\u5269\u4f59\u65f6\u95f4\uff1a", None))
        self.lbl_product_2.setText(QCoreApplication.translate("MainWidget", u"\u4ea7\u54c1\u578b\u53f7\uff1a", None))
        self.lbl_aging_time_2.setText(QCoreApplication.translate("MainWidget", u"\u8001\u5316\u65f6\u95f4\uff1a", None))
        self.lbl_qty_2.setText(QCoreApplication.translate("MainWidget", u"\u6570\u91cf\uff1a", None))
        self.edit_qty_2.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_good_2.setText(QCoreApplication.translate("MainWidget", u"\u826f\u54c1\uff1a", None))
        self.edit_good_2.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_bad_2.setText(QCoreApplication.translate("MainWidget", u"\u4e0d\u826f\u54c1\uff1a", None))
        self.edit_bad_2.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_pass_rate_2.setText(QCoreApplication.translate("MainWidget", u"\u5408\u683c\u7387\uff1a", None))
        self.text_pass_rate_2.setText(QCoreApplication.translate("MainWidget", u"0.00%", None))
        self.lbl_fail_rate_2.setText(QCoreApplication.translate("MainWidget", u"\u4e0d\u826f\u7387\uff1a", None))
        self.text_fail_rate_2.setText(QCoreApplication.translate("MainWidget", u"0.00%", None))
        self.lbl_temp_2.setText(QCoreApplication.translate("MainWidget", u"\u5f53\u524d\u6e29\u5ea6\uff1a", None))
        self.text_temp_2.setText(QCoreApplication.translate("MainWidget", u"0\u00b0", None))
        self.lbl_worker_2.setText(QCoreApplication.translate("MainWidget", u"\u64cd\u4f5c\u4eba\u5458\uff1a", None))
        self.lbl_start_time_2.setText(QCoreApplication.translate("MainWidget", u"\u5f00\u59cb\u65f6\u95f4\uff1a", None))
        self.text_start_time_2.setText(QCoreApplication.translate("MainWidget", u"--", None))
        self.lbl_end_time_2.setText(QCoreApplication.translate("MainWidget", u"\u7ed3\u675f\u65f6\u95f4\uff1a", None))
        self.text_end_time_2.setText(QCoreApplication.translate("MainWidget", u"--", None))
        self.btn_start_2.setText(QCoreApplication.translate("MainWidget", u"\u542f\u52a8\u8001\u5316", None))
        self.btn_pause_2.setText(QCoreApplication.translate("MainWidget", u"\u6682\u505c", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("MainWidget", u"\u7b2c3\u7ec4", None))
        self.lbl_runtime_3.setText(QCoreApplication.translate("MainWidget", u"\u8fd0\u884c\u65f6\u95f4\uff1a", None))
        self.lbl_remaining_3.setText(QCoreApplication.translate("MainWidget", u"\u5269\u4f59\u65f6\u95f4\uff1a", None))
        self.lbl_product_3.setText(QCoreApplication.translate("MainWidget", u"\u4ea7\u54c1\u578b\u53f7\uff1a", None))
        self.lbl_aging_time_3.setText(QCoreApplication.translate("MainWidget", u"\u8001\u5316\u65f6\u95f4\uff1a", None))
        self.lbl_qty_3.setText(QCoreApplication.translate("MainWidget", u"\u6570\u91cf\uff1a", None))
        self.edit_qty_3.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_good_3.setText(QCoreApplication.translate("MainWidget", u"\u826f\u54c1\uff1a", None))
        self.edit_good_3.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_bad_3.setText(QCoreApplication.translate("MainWidget", u"\u4e0d\u826f\u54c1\uff1a", None))
        self.edit_bad_3.setText(QCoreApplication.translate("MainWidget", u"0 Pcs", None))
        self.lbl_pass_rate_3.setText(QCoreApplication.translate("MainWidget", u"\u5408\u683c\u7387\uff1a", None))
        self.text_pass_rate_3.setText(QCoreApplication.translate("MainWidget", u"0.00%", None))
        self.lbl_fail_rate_3.setText(QCoreApplication.translate("MainWidget", u"\u4e0d\u826f\u7387\uff1a", None))
        self.text_fail_rate_3.setText(QCoreApplication.translate("MainWidget", u"0.00%", None))
        self.lbl_temp_3.setText(QCoreApplication.translate("MainWidget", u"\u5f53\u524d\u6e29\u5ea6\uff1a", None))
        self.text_temp_3.setText(QCoreApplication.translate("MainWidget", u"0\u00b0", None))
        self.lbl_worker_3.setText(QCoreApplication.translate("MainWidget", u"\u64cd\u4f5c\u4eba\u5458\uff1a", None))
        self.lbl_start_time_3.setText(QCoreApplication.translate("MainWidget", u"\u5f00\u59cb\u65f6\u95f4\uff1a", None))
        self.text_start_time_3.setText(QCoreApplication.translate("MainWidget", u"--", None))
        self.lbl_end_time_3.setText(QCoreApplication.translate("MainWidget", u"\u7ed3\u675f\u65f6\u95f4\uff1a", None))
        self.text_end_time_3.setText(QCoreApplication.translate("MainWidget", u"--", None))
        self.btn_start_3.setText(QCoreApplication.translate("MainWidget", u"\u542f\u52a8\u8001\u5316", None))
        self.btn_pause_3.setText(QCoreApplication.translate("MainWidget", u"\u6682\u505c", None))
        self.btn_history_refresh.setText(QCoreApplication.translate("MainWidget", u"\u5237\u65b0", None))
        self.btn_history_export.setText(QCoreApplication.translate("MainWidget", u"\u5bfc\u51fa\u6c47\u603b\u8868", None))
        self.lbl_history_year.setText(QCoreApplication.translate("MainWidget", u"\u5e74\uff1a", None))
        self.lbl_history_month.setText(QCoreApplication.translate("MainWidget", u"\u6708\uff1a", None))
        self.lbl_history_day.setText(QCoreApplication.translate("MainWidget", u"\u65e5\uff1a", None))
        self.btn_history_query.setText(QCoreApplication.translate("MainWidget", u"\u67e5\u8be2", None))
        self.aboutTitle.setText(QCoreApplication.translate("MainWidget", u"\u94a7\u6377\u667a\u80fd - \u667a\u80fd\u8001\u5316\u76d1\u63a7\u7cfb\u7edf", None))
        self.aboutVersion.setText(QCoreApplication.translate("MainWidget", u"Version: 1.0.0 (Build 2025)", None))
        self.aboutCopyright.setText(QCoreApplication.translate("MainWidget", u"Copyright \u00a9 2025 Jun Jie Tech. All rights reserved.", None))
        self.aboutWebsite.setText(QCoreApplication.translate("MainWidget", u"Website: https://www.junjiesz.com", None))
        self.aboutEmail.setText(QCoreApplication.translate("MainWidget", u"Email: chenjintao@junjietech.com", None))
        pass
    # retranslateUi

