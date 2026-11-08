import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "appUpdateDialog"
    required property var updates
    property bool workActive: false
    anchors.centerIn: parent
    width: Math.min(parent.width - 48, 560)
    height: Math.min(parent.height - 48, updateContent.implicitHeight + 144)
    modal: true
    title: updates.available ? "有新的 App 版本" : "App 更新"
    background: Rectangle { color: Theme.panel; radius: 12; border.color: Theme.line }
    contentItem: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            id: updateContent
            width: parent.width
            spacing: 16
            RowLayout {
                Layout.fillWidth: true
                Rectangle {
                    width: 44; height: 44; radius: 12; color: Theme.accentDark
                    Icon { name: "download"; anchors.centerIn: parent; width: 22; height: 22 }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Text { text: "Video Downloader"; color: Theme.text; font.pixelSize: 18; font.weight: Font.Medium }
                    Text { text: "目前版本 " + updates.currentVersion + (updates.available ? "   →   " + updates.latestVersion : ""); color: Theme.secondary; font.pixelSize: 13 }
                }
            }
            Text { Layout.fillWidth: true; text: updates.status; color: updates.state === "error" ? Theme.warning : Theme.secondary; wrapMode: Text.Wrap; font.pixelSize: 13; textFormat: Text.PlainText }
            ProgressBar {
                Layout.fillWidth: true
                visible: updates.busy || updates.state === "ready" || updates.state === "installing"
                indeterminate: updates.state === "checking" || updates.state === "ready" || updates.state === "installing"
                from: 0; to: 100; value: Math.max(0, updates.progress)
                palette.highlight: Theme.accent
            }
            Text {
                visible: updates.state === "downloading"
                text: "下載進度 " + updates.progress + "%  ·  " + updates.downloadSize
                color: Theme.muted; font.pixelSize: 12
            }
            Rectangle {
                visible: updates.available
                Layout.fillWidth: true; implicitHeight: notesColumn.implicitHeight + 32
                color: Theme.bg; radius: 8; border.color: Theme.line
                ColumnLayout {
                    id: notesColumn
                    anchors.fill: parent; anchors.margins: 16; spacing: 8
                    Text { text: "更新內容"; color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
                    Text { Layout.fillWidth: true; text: updates.notes; textFormat: Text.PlainText; color: Theme.secondary; font.pixelSize: 13; wrapMode: Text.Wrap; lineHeight: 1.2 }
                }
            }
            Text {
                Layout.fillWidth: true; visible: updates.available
                text: updates.installPending && workActive ? "更新已排程，會等目前工作結束後自動安裝。你可以取消更新並繼續使用。" : "更新整個 App，保留設定、任務紀錄與下載檔案。完成後會重新啟動；新版無法啟動時會回復原版本。"
                color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
            }
            Text { Layout.fillWidth: true; text: "更新來源：" + updates.repository; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap }
        }
    }
    footer: DialogButtonBox {
        VButton { text: updates.installPending ? "在背景繼續" : "稍後"; onClicked: dialog.close() }
        VButton { visible: updates.busy || updates.installPending; text: "取消更新"; enabled: updates.state !== "installing"; onClicked: updates.cancel() }
        VButton { visible: !updates.installPending; text: "重新檢查"; enabled: !updates.busy; onClicked: updates.checkNow() }
        VButton {
            objectName: "installAppUpdateButton"
            visible: updates.available && !updates.installPending
            text: workActive ? "工作結束後更新" : "下載並更新"
            primary: true; enabled: !updates.busy
            onClicked: updates.download()
        }
    }
}
