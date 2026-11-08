import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    visible: true
    width: 1120; height: 850
    minimumWidth: 900; minimumHeight: 640
    title: "Video Downloader"
    color: Theme.bg
    font.family: "Microsoft JhengHei UI"
    font.pixelSize: 14
    palette.window: Theme.panel
    palette.windowText: Theme.text
    palette.text: Theme.text
    palette.buttonText: Theme.text
    palette.base: Theme.raised
    palette.highlight: Theme.accent
    palette.highlightedText: "#10223a"
    property bool allowClose: false
    property bool showAdvanced: false
    onClosing: function(event) {
        if (!allowClose && !backend.requestClose()) { event.accepted = false; closeDialog.open() }
    }
    Connections {
        target: backend
        function onMessage(text) { toastText.text = text; toast.visible = true; toastTimer.restart() }
        function onShutdownReady() { win.allowClose = true; Qt.quit() }
    }
    Connections {
        target: backend.appUpdates
        function onPrompt() { appUpdateDialog.open() }
    }

    header: Rectangle {
        height: 68; color: Theme.bg
        Rectangle { height: 1; color: Theme.line; anchors.bottom: parent.bottom; width: parent.width }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 24; spacing: 12
            Rectangle { width: 32; height: 32; radius: 9; color: Theme.accentDark; Icon { anchors.centerIn: parent; name: "download"; width: 20; height: 20 } }
            Text { text: "Video Downloader"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
            Text { text: "影音下載工具"; color: Theme.muted; font.pixelSize: 12; Layout.leftMargin: 4 }
            Item { Layout.fillWidth: true }
            Text { text: backend.activeCount > 0 ? backend.activeCount + " 個任務處理中" : "本機執行"; color: backend.activeCount > 0 ? Theme.accent : Theme.muted; font.pixelSize: 12 }
            Item {
                implicitWidth: appUpdateButton.implicitWidth + 8; implicitHeight: 40
                VButton {
                    id: appUpdateButton; objectName: "appUpdateButton"
                    text: backend.appUpdates.installPending ? "更新處理中" : "檢查更新"
                    quiet: true
                    onClicked: { appUpdateDialog.open(); if (!backend.appUpdates.available && !backend.appUpdates.busy) backend.appUpdates.checkNow() }
                }
                Rectangle { objectName: "appUpdateDot"; visible: backend.appUpdates.available; width: 7; height: 7; radius: 4; color: Theme.negative; anchors.right: parent.right; anchors.top: parent.top; anchors.topMargin: 5; Accessible.name: "有新的 App 版本" }
            }
            VButton { text: "設定"; glyph: "settings"; quiet: true; onClicked: settingsDialog.open() }
        }
    }

    ScrollView {
        id: page
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: page.availableWidth
            spacing: 0
            Item { Layout.preferredHeight: 28 }
            ColumnLayout {
                Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32; spacing: 20
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        spacing: 6
                        Text { text: "把影音，留在電腦裡"; color: Theme.text; font.pixelSize: 28; font.weight: Font.Medium }
                        Text { text: "貼上 YouTube 連結，選擇影片或音訊，儲存到你的位置"; color: Theme.secondary; font.pixelSize: 13 }
                    }
                    Item { Layout.fillWidth: true }
                    Text { text: "YouTube ／ Shorts"; color: Theme.muted; font.pixelSize: 12 }
                }

                Rectangle {
                    Layout.fillWidth: true; implicitHeight: 92
                    color: Theme.panel; radius: Theme.radius; border.color: Theme.line
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 16; spacing: 8
                        Text { text: "影片網址"; color: Theme.secondary; font.pixelSize: 12 }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            TextField {
                                id: urlField
                                objectName: "urlField"
                                focus: true
                                Layout.fillWidth: true; Layout.preferredHeight: 40
                                placeholderText: "在這裡貼上 YouTube 網址（Ctrl+V）"
                                placeholderTextColor: Theme.muted
                                color: Theme.text; font.pixelSize: 13; selectByMouse: true
                                Accessible.name: "YouTube 影片網址"
                                background: Rectangle { color: Theme.bg; radius: 7; border.color: urlField.activeFocus ? Theme.accent : Theme.line; border.width: urlField.activeFocus ? 2 : 1 }
                                onAccepted: backend.parse(text)
                                onTextEdited: { backend.inputEdited(text); autoParse.stop(); if (text.trim().length > 15) autoParse.restart() }
                                Timer { id: autoParse; interval: 800; onTriggered: backend.parse(urlField.text) }
                                TapHandler {
                                    acceptedButtons: Qt.RightButton
                                    onTapped: function(eventPoint) { urlField.forceActiveFocus(); editMenu.popup(eventPoint.position.x, eventPoint.position.y) }
                                }
                                Menu {
                                    id: editMenu
                                    MenuItem { text: "剪下"; enabled: urlField.selectedText.length > 0; onTriggered: urlField.cut() }
                                    MenuItem { text: "複製"; enabled: urlField.selectedText.length > 0; onTriggered: urlField.copy() }
                                    MenuItem { objectName: "pasteUrlAction"; text: "貼上"; enabled: urlField.canPaste; onTriggered: urlField.paste() }
                                    MenuSeparator {}
                                    MenuItem { text: "全選"; enabled: urlField.length > 0; onTriggered: urlField.selectAll() }
                                }
                            }
                            VButton { text: "貼上"; glyph: "clipboard"; onClicked: { urlField.text = backend.clipboard(); if (urlField.text) backend.parse(urlField.text) } }
                            VButton { text: backend.busy ? "停止解析" : "解析影片"; primary: !backend.busy; onClicked: backend.busy ? backend.cancelParse() : backend.parse(urlField.text) }
                        }
                    }
                }

                Rectangle {
                    visible: backend.error !== ""
                    Layout.fillWidth: true; implicitHeight: errorRow.implicitHeight + 24
                    radius: 8; color: "#2b2023"; border.color: "#57383d"
                    RowLayout {
                        id: errorRow
                        anchors.fill: parent; anchors.margins: 12; spacing: 12
                        Icon { name: "alert-circle" }
                        Text { text: backend.error; color: Theme.negative; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        VButton { text: "複製診斷"; quiet: true; onClicked: backend.copyDiagnostic("") }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true; spacing: 20
                    Layout.alignment: Qt.AlignTop
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: backend.mode === "audio" ? 440 : 370; Layout.alignment: Qt.AlignTop
                        color: Theme.panel; radius: Theme.radius; border.color: Theme.line
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 20; spacing: 16
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "來源預覽"; color: Theme.secondary; font.pixelSize: 12 }
                                Item { Layout.fillWidth: true }
                                VButton { text: win.showAdvanced ? "收合詳情" : "來源詳情"; quiet: true; selected: win.showAdvanced; implicitHeight: 24; enabled: !!backend.media.title; onClicked: win.showAdvanced = !win.showAdvanced }
                                Text { text: backend.media.type || "等待連結"; color: Theme.muted; font.pixelSize: 12 }
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                color: "#131619"; radius: 8; clip: true
                                Image { id: thumbnail; anchors.fill: parent; source: backend.media.thumbnail || ""; asynchronous: true; fillMode: Image.PreserveAspectCrop; visible: backend.media.title !== undefined; sourceSize.width: 960 }
                                Rectangle {
                                    visible: !!backend.media.duration; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 12
                                    color: "#d0111315"; radius: 4; width: durationLabel.implicitWidth + 16; height: 26
                                    Text { id: durationLabel; anchors.centerIn: parent; text: backend.media.duration || ""; color: "white"; font.pixelSize: 12; font.family: "Consolas" }
                                }
                                Column {
                                    anchors.centerIn: parent; spacing: 14; visible: !backend.media.title
                                    Rectangle {
                                        width: 56; height: 56; radius: 16; color: Theme.raised; anchors.horizontalCenter: parent.horizontalCenter
                                        Icon { anchors.centerIn: parent; name: backend.busy ? "link" : "video"; width: 28; height: 28 }
                                    }
                                    Text { text: backend.busy ? "正在讀取影片資訊" : "從一個連結開始"; color: Theme.text; font.pixelSize: 17; anchors.horizontalCenter: parent.horizontalCenter }
                                    Text { text: backend.busy ? "取得來源提供的真實畫質與音訊" : "一般影片或 Shorts，都放在這裡"; color: Theme.muted; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
                                    ProgressBar { width: 160; anchors.horizontalCenter: parent.horizontalCenter; visible: backend.busy; indeterminate: true; palette.highlight: Theme.accent }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 6
                                Text { Layout.fillWidth: true; text: backend.media.title || "影片資訊會顯示在這裡"; color: backend.media.title ? Theme.text : Theme.secondary; font.pixelSize: 16; font.weight: Font.Medium; maximumLineCount: 2; elide: Text.ElideRight; wrapMode: Text.Wrap; ToolTip.visible: titleHover.hovered && !!backend.media.title; ToolTip.text: backend.media.title || ""; HoverHandler { id: titleHover } }
                                Text { Layout.fillWidth: true; text: backend.media.title ? (backend.media.channel + (backend.media.date ? "  ·  " + backend.media.date : "")) : "解析完成後，可選擇來源實際提供的規格"; color: Theme.muted; font.pixelSize: 12; elide: Text.ElideRight }
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 340; Layout.preferredHeight: backend.mode === "audio" ? 440 : 370; Layout.alignment: Qt.AlignTop
                        color: Theme.panel; radius: Theme.radius; border.color: Theme.line
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 20; spacing: 12
                            RowLayout {
                                spacing: 4; Layout.fillWidth: true
                                Repeater {
                                    model: ["下載影片", "僅下載音訊"]
                                    delegate: VButton {
                                        required property int index
                                        required property string modelData
                                        Layout.fillWidth: true
                                        text: modelData
                                        selected: (index === 0 && backend.mode === "video") || (index === 1 && backend.mode === "audio")
                                        onClicked: backend.select("mode", index === 0 ? "video" : "audio")
                                    }
                                }
                            }
                            ColumnLayout {
                                spacing: 6; Layout.fillWidth: true
                                Text { text: backend.mode === "video" ? "來源畫質" : "來源音訊"; color: Theme.secondary; font.pixelSize: 12 }
                                VCombo {
                                    objectName: "qualityCombo"
                                    Layout.fillWidth: true
                                    enabled: !!backend.media.title
                                    model: backend.mode === "video" ? backend.videoOptions : backend.audioOptions
                                    currentIndex: backend.mode === "video" ? backend.qualityIndex : backend.audioIndex
                                    displayText: count ? currentText : "解析後選擇"
                                    onActivated: function(index) { backend.select(backend.mode === "video" ? "quality_index" : "audio_index", index.toString()) }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 12
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 6
                                    Text { text: "輸出格式"; color: Theme.secondary; font.pixelSize: 12 }
                                    VCombo {
                                        Layout.fillWidth: true; enabled: !!backend.media.title
                                        model: backend.mode === "video" ? ["MP4（推薦）", "MKV", "WebM"] : ["保留原始音訊", "MP3", "M4A", "Opus", "WAV"]
                                        currentIndex: backend.mode === "video" ? ["mp4", "mkv", "webm"].indexOf(backend.container) : ["original", "mp3", "m4a", "opus", "wav"].indexOf(backend.audioFormat)
                                        onActivated: function(index) { backend.select(backend.mode === "video" ? "container" : "audio_format", backend.mode === "video" ? ["mp4", "mkv", "webm"][index] : ["original", "mp3", "m4a", "opus", "wav"][index]) }
                                    }
                                }
                                ColumnLayout {
                                    visible: backend.mode === "audio" && ["mp3", "m4a", "opus"].indexOf(backend.audioFormat) >= 0 && backend.needsConversion
                                    Layout.preferredWidth: 116; spacing: 6
                                    Text { text: "輸出位元率"; color: Theme.secondary; font.pixelSize: 12 }
                                    VCombo { Layout.fillWidth: true; model: ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]; currentIndex: ["128", "192", "256", "320"].indexOf(backend.bitrate); onActivated: function(index) { backend.select("bitrate", ["128", "192", "256", "320"][index]) } }
                                }
                            }
                            Text {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                Layout.minimumHeight: implicitHeight
                                text: backend.summary + (backend.mode === "audio" && backend.media.title ? "\n" + backend.sourceDetail : "")
                                color: backend.needsConversion ? Theme.warning : Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; lineHeight: 1.2
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Icon { name: "folder"; width: 16; height: 16 }
                                Text { Layout.fillWidth: true; text: backend.settings.folder; color: Theme.secondary; font.pixelSize: 12; elide: Text.ElideMiddle; ToolTip.visible: folderHover.hovered; ToolTip.text: backend.settings.folder; HoverHandler { id: folderHover } }
                                VButton { text: "變更"; quiet: true; implicitHeight: 28; onClicked: backend.chooseFolder() }
                            }
                            VButton {
                                Layout.fillWidth: true; implicitHeight: 44; primary: true
                                text: backend.needsConversion ? "確認轉換並加入下載" : "加入下載佇列"
                                enabled: backend.canDownload
                                onClicked: { if (backend.needsConversion) conversionDialog.open(); else backend.enqueue() }
                            }
                        }
                    }
                }

                Rectangle {
                    visible: win.showAdvanced && !!backend.media.title
                    Layout.fillWidth: true; implicitHeight: advancedColumn.implicitHeight + 32
                    color: Theme.panel; radius: Theme.radius; border.color: Theme.line
                    ColumnLayout {
                        id: advancedColumn
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 8
                        Text { text: "來源音軌"; color: Theme.secondary; font.pixelSize: 12 }
                        VCombo { Layout.fillWidth: true; model: backend.audioOptions; currentIndex: backend.audioIndex; onActivated: function(index) { backend.select("audio_index",index.toString()) } }
                        Text { text: backend.sourceSize; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true; Layout.topMargin: 8
                    Text { text: "下載任務"; color: Theme.text; font.pixelSize: 17; font.weight: Font.Medium }
                    Text { text: backend.taskCount.toString(); color: Theme.muted; font.pixelSize: 13 }
                    Item { Layout.fillWidth: true }
                    Text { text: "最多同時 " + backend.settings.concurrency + " 個 · 完成後驗證輸出"; color: Theme.muted; font.pixelSize: 12 }
                }

                Rectangle {
                    visible: backend.taskCount === 0
                    Layout.fillWidth: true; implicitHeight: 108
                    color: "transparent"; radius: Theme.radius; border.color: Theme.line
                    RowLayout {
                        anchors.centerIn: parent; spacing: 16
                        Icon { name: "inbox"; width: 32; height: 32 }
                        ColumnLayout {
                            spacing: 6
                            Text { text: "還沒有下載任務"; color: Theme.secondary; font.pixelSize: 14 }
                            Text { text: "選好規格後加入佇列，下載進度會出現在這裡"; color: Theme.muted; font.pixelSize: 12 }
                        }
                    }
                }
                Repeater {
                    model: backend.tasks
                    delegate: Rectangle {
                        required property var item
                        Layout.fillWidth: true; implicitHeight: taskColumn.implicitHeight + 32; Layout.bottomMargin: -8
                        color: Theme.panel; radius: Theme.radius; border.color: Theme.line
                        ColumnLayout {
                            id: taskColumn
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 10
                            RowLayout {
                                Layout.fillWidth: true; spacing: 12
                                Rectangle { width: 72; height: 44; radius: 6; color: Theme.raised; clip: true; Image { anchors.fill: parent; source: item.thumbnail || ""; asynchronous: true; sourceSize.width: 144; fillMode: Image.PreserveAspectCrop } }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 4
                                    Text { text: item.title; color: Theme.text; Layout.fillWidth: true; font.pixelSize: 13; elide: Text.ElideRight }
                                    Text { text: item.plan.summary; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                                }
                                Text { text: item.stateLabel; color: item.state === "completed" ? Theme.positive : item.state === "failed" ? Theme.negative : item.active ? Theme.accent : Theme.secondary; font.pixelSize: 12 }
                                VButton { visible: item.active || item.state === "recoverable"; text: "取消"; quiet: true; implicitHeight: 32; enabled: item.state !== "cancelling"; onClicked: backend.cancel(item.id) }
                                VButton { visible: ["failed", "cancelled", "recoverable"].indexOf(item.state) >= 0; text: "重試"; glyph: "refresh"; implicitHeight: 32; onClicked: backend.retry(item.id) }
                                VButton { visible: item.state === "completed"; text: "開啟檔案"; implicitHeight: 32; onClicked: backend.openFile(item.id) }
                                VButton { visible: item.state === "completed"; text: "資料夾"; glyph: "folder"; quiet: true; implicitHeight: 32; onClicked: backend.openFolder(item.id) }
                            }
                            ProgressBar {
                                Layout.fillWidth: true; visible: item.active; from: 0; to: 100; value: item.progress >= 0 ? item.progress : 0; indeterminate: item.progress < 0
                                implicitHeight: 4
                                background: Rectangle { implicitHeight: 4; color: Theme.raised; radius: 2 }
                                contentItem: Item {
                                    implicitHeight: 4; clip: true
                                    Rectangle {
                                        id: progressFill
                                        width: item.progress < 0 ? (backend.reducedMotion ? parent.width : parent.width * 0.25) : parent.width * Math.max(0,item.progress)/100
                                        height: 4; radius: 2; color: Theme.accent; opacity: item.progress < 0 ? 0.55 : 1
                                        NumberAnimation on x { from: 0; to: progressFill.parent.width-progressFill.width; duration: 1400; loops: Animation.Infinite; running: item.active && item.progress < 0 && !backend.reducedMotion; onRunningChanged: { if(!running) progressFill.x=0 } }
                                        Behavior on width { NumberAnimation { duration: Theme.duration } }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: item.detail || ""; Layout.fillWidth: true; color: item.state === "failed" ? Theme.negative : Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
                                Text { text: (item.speed || "") + (item.eta ? "  ·  剩餘 " + item.eta : ""); color: Theme.secondary; font.pixelSize: 12; font.family: "Consolas" }
                                VButton { visible: item.state === "failed"; text: "診斷"; quiet: true; implicitHeight: 28; onClicked: backend.copyDiagnostic(item.id) }
                                VButton { visible: item.state === "failed"; text: "另存位置"; quiet: true; implicitHeight: 28; onClicked: backend.saveElsewhere(item.id) }
                                VButton { visible: !item.active; text: "移除"; quiet: true; implicitHeight: 28; onClicked: backend.remove(item.id) }
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true; Layout.topMargin: 4; Layout.bottomMargin: 24
                    Icon { name: "shield"; width: 14; height: 14 }
                    Text { text: "檔案與任務紀錄保留在本機"; color: Theme.muted; font.pixelSize: 11 }
                    Item { Layout.fillWidth: true }
                    Text { text: "請依來源授權與平台規則使用"; color: Theme.muted; font.pixelSize: 11 }
                }
            }
        }
    }

    Dialog {
        id: conversionDialog
        anchors.centerIn: parent; width: 480; modal: true; title: "確認重新編碼"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { standardButton(Dialog.Ok).text = "確認並開始"; standardButton(Dialog.Cancel).text = "返回" }
        onAccepted: backend.enqueue()
        contentItem: Label { text: backend.summary + "\n\n此設定需要重新編碼，可能花費較長時間並增加 CPU 使用。轉換不會提升來源本身品質。"; color: Theme.text; wrapMode: Text.Wrap; padding: 12 }
        background: Rectangle { color: Theme.panel; radius: 12; border.color: Theme.line }
    }
    AppUpdateDialog { id: appUpdateDialog; updates: backend.appUpdates; workActive: backend.activeCount > 0 || backend.busy || backend.updateBusy }
    Dialog {
        id: closeDialog
        anchors.centerIn: parent; width: 460; modal: true; title: "仍有工作正在處理"
        contentItem: Label { text: backend.updateBusy ? "核心更新正在處理中，請等待完成後再結束。" : "結束會停止目前的工作。可用暫存會保留，重新開啟後可選擇重試。"; color: Theme.secondary; wrapMode: Text.Wrap; padding: 12 }
        footer: DialogButtonBox {
            VButton { text: "繼續使用"; DialogButtonBox.buttonRole: DialogButtonBox.RejectRole; onClicked: closeDialog.close() }
            VButton { text: "停止任務並結束"; enabled: !backend.updateBusy; DialogButtonBox.buttonRole: DialogButtonBox.DestructiveRole; onClicked: { closeDialog.close(); backend.shutdown() } }
        }
        background: Rectangle { color: Theme.panel; radius: 12; border.color: Theme.line }
    }
    Dialog {
        id: settingsDialog
        objectName: "settingsDialog"
        anchors.centerIn: parent; width: 600; height: Math.min(win.height - 64, 720); modal: true; title: "設定"
        standardButtons: Dialog.Close
        onOpened: standardButton(Dialog.Close).text = "關閉"
        background: Rectangle { color: Theme.panel; radius: 12; border.color: Theme.line }
        contentItem: ScrollView {
            clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 16
                Text { text: "下載偏好"; color: Theme.text; font.pixelSize: 16 }
                Text { text: "儲存資料夾"; color: Theme.secondary; font.pixelSize: 12 }
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: backend.settings.folder; color: Theme.text; Layout.fillWidth: true; font.pixelSize: 12; elide: Text.ElideMiddle }
                    VButton { text: "選擇資料夾"; onClicked: backend.chooseFolder() }
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text { text: "預設模式"; color: Theme.secondary; font.pixelSize: 12 }
                        VCombo { Layout.fillWidth: true; model: ["下載影片", "僅下載音訊"]; currentIndex: backend.settings.mode === "video" ? 0 : 1; onActivated: function(index) { backend.setSetting("mode", index === 0 ? "video" : "audio") } }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text { text: "預設品質策略"; color: Theme.secondary; font.pixelSize: 12 }
                        VCombo { Layout.fillWidth: true; model: ["建議品質", "最高來源品質"]; currentIndex: backend.settings.strategy === "recommended" ? 0 : 1; onActivated: function(index) { backend.setSetting("strategy", index === 0 ? "recommended" : "best") } }
                    }
                    ColumnLayout {
                        Layout.preferredWidth: 104; spacing: 6
                        Text { text: "同時下載數"; color: Theme.secondary; font.pixelSize: 12 }
                        VCombo { Layout.fillWidth: true; model: ["1", "2", "3"]; currentIndex: backend.settings.concurrency - 1; onActivated: function(index) { backend.setSetting("concurrency", index + 1) } }
                    }
                }
                Text { text: "建議品質優先選擇相容串流；最高來源品質可能使用較新的編碼。偏好會套用至下次解析。"; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                CheckBox { text: "下載完成時顯示通知"; checked: backend.settings.notifications; onToggled: backend.setSetting("notifications", checked) }
                CheckBox { text: "減少介面動畫"; checked: backend.settings.reduceMotion; onToggled: backend.setSetting("reduceMotion", checked) }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }
                Text { text: "App 更新"; color: Theme.text; font.pixelSize: 16 }
                Text { text: "目前版本 " + backend.appUpdates.currentVersion + "  ·  更新整個程式與所有功能"; color: Theme.secondary; font.pixelSize: 12 }
                Text { Layout.fillWidth: true; text: backend.appUpdates.status; textFormat: Text.PlainText; color: Theme.muted; wrapMode: Text.Wrap; font.pixelSize: 12 }
                CheckBox { text: "開啟 App 時自動檢查更新"; checked: backend.appUpdates.autoCheck; onToggled: backend.appUpdates.setAutoCheck(checked) }
                CheckBox { text: "發現新版本時顯示提示視窗"; checked: backend.appUpdates.showPrompts; onToggled: backend.appUpdates.setShowPrompts(checked) }
                VButton { text: "查看 App 更新"; onClicked: { appUpdateDialog.open(); if (!backend.appUpdates.available && !backend.appUpdates.busy) backend.appUpdates.checkNow() } }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }
                Text { text: "下載核心與依賴"; color: Theme.text; font.pixelSize: 16 }
                Repeater {
                    model: ["yt-dlp", "ffmpeg", "ffprobe", "deno"]
                    delegate: RowLayout {
                        required property string modelData
                        Layout.fillWidth: true
                        Text { text: modelData; color: Theme.secondary; font.pixelSize: 12; Layout.preferredWidth: 72 }
                        Text { text: backend.versions[modelData]; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight; ToolTip.visible: versionHover.hovered; ToolTip.text: text; HoverHandler { id: versionHover } }
                    }
                }
                Text { text: !backend.updateBusy && backend.updateMessage.indexOf("官方穩定版：") === 0 && backend.latestVersion === backend.versions["yt-dlp"] ? "目前已是最新穩定版（" + backend.latestVersion + "）" : backend.updateMessage; color: Theme.secondary; wrapMode: Text.Wrap; font.pixelSize: 12; Layout.fillWidth: true }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    VButton { text: "檢查核心更新"; enabled: !backend.updateBusy; onClicked: backend.checkUpdate() }
                    VButton { text: "安裝核心更新"; enabled: backend.latestVersion !== "" && backend.latestVersion !== backend.versions["yt-dlp"] && !backend.updateBusy && !backend.appUpdates.installPending && backend.activeCount === 0 && !backend.busy; onClicked: updateDialog.open() }
                    VButton { text: "回復隨附核心"; quiet: true; enabled: !backend.updateBusy; onClicked: backend.rollbackCore() }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }
                Text { text: "暫存與隱私"; color: Theme.text; font.pixelSize: 16 }
                Text { text: "失敗或取消的暫存保留 7 天供重試；清理只移除本工具管理且已到期的工作區。下載成果不會刪除。\n解析、下載與更新會連線至來源平台及官方元件服務，任務紀錄不會上傳。"; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                VButton { text: "清理已到期暫存"; glyph: "trash"; onClicked: backend.cleanTemp() }
                Text { text: "Video Downloader " + backend.appUpdates.currentVersion + "  ·  深色主題"; color: Theme.muted; font.pixelSize: 11; Layout.topMargin: 8 }
            }
        }
    }
    Dialog {
        id: updateDialog
        anchors.centerIn: parent; width: 500; modal: true; title: "安裝下載核心更新"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { standardButton(Dialog.Ok).text = "下載並驗證"; standardButton(Dialog.Cancel).text = "取消" }
        contentItem: Label { text: "目標版本：" + backend.latestVersion + "\n來源：github.com/yt-dlp/yt-dlp 官方發行\n\n將驗證官方 SHA256 與啟動能力後切換版本。失敗時保留既有版本；可在設定回復隨附核心。"; color: Theme.secondary; wrapMode: Text.Wrap; padding: 12 }
        onAccepted: backend.installUpdate()
        background: Rectangle { color: Theme.panel; radius: 12; border.color: Theme.line }
    }

    Rectangle {
        id: toast
        visible: false; z: 100
        anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 24
        width: Math.min(win.width - 80, toastText.implicitWidth + 40); height: toastText.implicitHeight + 28
        color: "#303741"; radius: 10; border.color: "#49515d"
        Text { id: toastText; anchors.fill: parent; anchors.margins: 14; color: Theme.text; font.pixelSize: 13; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
        Timer { id: toastTimer; interval: 6500; onTriggered: toast.visible = false }
    }
}
