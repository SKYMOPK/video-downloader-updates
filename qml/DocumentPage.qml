import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: page
    property var documents: backend.documents
    objectName: "documentPage"
    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ColumnLayout {
        width: page.availableWidth
        spacing: 20
        Item { Layout.preferredHeight: 6 }
        ColumnLayout {
            Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32; spacing: 8
            Text { text: "讓文件，換個好用的格式"; color: Theme.text; font.pixelSize: 28; font.weight: Font.Medium }
            Text { text: "加入檔案，自動辨識內容，再選擇適合的輸出格式。全程在電腦中處理。"; color: Theme.secondary; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32; implicitHeight: 148
            radius: Theme.radius; color: drop.containsDrag ? Theme.accentDark : Theme.panel
            border.color: drop.containsDrag ? Theme.accent : Theme.line; border.width: drop.containsDrag ? 2 : 1
            DropArea {
                id: drop; anchors.fill: parent
                onDropped: function(event) { if (event.hasUrls) { page.documents.addFiles(event.urls); event.acceptProposedAction() } }
            }
            ColumnLayout {
                anchors.centerIn: parent; spacing: 8
                Text { text: drop.containsDrag ? "放開即可加入檔案" : "把文件或圖片拖曳到這裡"; color: Theme.text; font.pixelSize: 17; Layout.alignment: Qt.AlignHCenter }
                Text { text: "Word、Excel、PowerPoint、PDF、文字與常見圖片 · 每個檔案上限 100 MB"; color: Theme.muted; font.pixelSize: 12; Layout.alignment: Qt.AlignHCenter }
                VButton { objectName: "chooseDocumentFiles"; text: "選擇檔案"; glyph: "plus"; Layout.alignment: Qt.AlignHCenter; onClicked: page.documents.chooseFiles() }
            }
        }
        Rectangle {
            visible: page.documents.error !== ""; Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
            implicitHeight: errorRow.implicitHeight+24; radius: 8; color: "#2b2023"; border.color: "#57383d"
            RowLayout {
                id: errorRow; anchors.fill: parent; anchors.margins: 12
                Text { text: page.documents.error; color: Theme.negative; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
                VButton { text: "關閉"; quiet: true; onClicked: page.documents.dismissError() }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32; implicitHeight: options.implicitHeight+32
            radius: Theme.radius; color: Theme.panel; border.color: Theme.line
            ColumnLayout {
                id: options; anchors.fill: parent; anchors.margins: 16; spacing: 14
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Text { text: "儲存位置"; color: Theme.secondary; font.pixelSize: 12 }
                    Text { text: page.documents.folder; color: Theme.text; elide: Text.ElideMiddle; Layout.fillWidth: true; font.pixelSize: 13
                        HoverHandler { id: folderHover }
                        ToolTip.visible: folderHover.hovered; ToolTip.text: text
                    }
                    VButton { text: "變更"; quiet: true; onClicked: page.documents.chooseFolder() }
                    VButton { text: "開啟資料夾"; glyph: "folder"; quiet: true; onClicked: page.documents.openFolder() }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Text { text: "批次格式"; color: Theme.secondary; font.pixelSize: 12 }
                    VCombo {
                        objectName: "documentBatchOutput"; Layout.preferredWidth: 172
                        model: page.documents.commonOptions; currentIndex: -1
                        displayText: page.documents.readyCount === 0 ? "加入檔案後選擇" : count === 0 ? "請逐項選擇格式" : "統一輸出格式…"
                        enabled: count > 0 && !page.documents.mergeImages
                        onActivated: function(index) { page.documents.setCommonOutput(index) }
                        Accessible.name: "統一設定待轉換檔案的輸出格式"
                    }
                    Item { Layout.fillWidth: true }
                    VButton { text: "停止全部"; visible: page.documents.activeCount > 0; onClicked: page.documents.cancelAll() }
                    VButton { objectName: "startDocumentConversion"; text: page.documents.readyCount > 0 ? "開始轉換（" + page.documents.readyCount + "）" : "開始轉換"; primary: true; enabled: page.documents.readyCount > 0 && !backend.appUpdates.installPending; onClicked: page.documents.start() }
                }
                CheckBox {
                    visible: page.documents.canMerge; text: "將待轉換的圖片依清單順序合併成一份 PDF"
                    checked: page.documents.mergeImages; onToggled: page.documents.setMerge(checked)
                    palette.windowText: Theme.secondary; font.pixelSize: 13
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
            Text { text: "轉換清單"; color: Theme.text; font.pixelSize: 17; font.weight: Font.Medium }
            Text { text: page.documents.count + " 個任務"; color: Theme.muted; font.pixelSize: 12 }
            Item { Layout.fillWidth: true }
            VButton { text: "清除已結束"; quiet: true; enabled: page.documents.count > 0; onClicked: page.documents.clearFinished() }
        }
        Rectangle {
            visible: page.documents.count === 0; Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
            implicitHeight: 100; color: "transparent"; radius: Theme.radius; border.color: Theme.line
            Text { anchors.centerIn: parent; text: "尚未加入檔案\n原始檔案會保留，同名結果會自動加上編號。"; horizontalAlignment: Text.AlignHCenter; lineHeight: 1.6; color: Theme.muted; font.pixelSize: 13 }
        }
        Repeater {
            model: page.documents.tasks
            delegate: Rectangle {
                id: card
                required property var item
                required property int index
                Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
                implicitHeight: content.implicitHeight+28; color: Theme.panel; radius: Theme.radius; border.color: item.state === "failed" ? "#57383d" : Theme.line
                ColumnLayout {
                    id: content; anchors.fill: parent; anchors.margins: 14; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true; spacing: 12
                        Rectangle {
                            width: 40; height: 44; radius: 7; color: Theme.raised
                            Text { anchors.centerIn: parent; text: card.item.format.toUpperCase(); color: Theme.accent; font.pixelSize: card.item.format.length > 3 ? 10 : 12; font.weight: Font.DemiBold }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: card.item.name; color: Theme.text; font.pixelSize: 14; elide: Text.ElideMiddle; Layout.fillWidth: true
                                HoverHandler { id: nameHover }
                                ToolTip.visible: nameHover.hovered; ToolTip.text: card.item.sources.join("\n")
                            }
                            Text { text: card.item.formatLabel + " · " + card.item.sizeText; color: Theme.muted; font.pixelSize: 12 }
                        }
                        Text { text: "轉成"; color: Theme.muted; font.pixelSize: 12 }
                        VCombo {
                            Layout.preferredWidth: 142; model: card.item.optionLabels
                            currentIndex: card.item.options.indexOf(card.item.output); enabled: card.item.editable && !page.documents.mergeImages
                            onActivated: function(index) { page.documents.setOutput(card.item.id,index) }
                            Accessible.name: card.item.name + "的輸出格式"
                        }
                        Text { text: card.item.stateLabel; color: card.item.state === "completed" ? Theme.positive : card.item.state === "failed" ? Theme.negative : card.item.active ? Theme.accent : Theme.muted; font.pixelSize: 12; Layout.preferredWidth: 54; horizontalAlignment: Text.AlignRight }
                    }
                    Text { text: card.item.warning; visible: card.item.state === "draft"; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        BusyIndicator { visible: card.item.state === "converting" || card.item.state === "cancelling"; running: visible; implicitWidth: 20; implicitHeight: 20 }
                        Text { text: card.item.detail || "準備就緒"; color: card.item.state === "failed" ? Theme.negative : Theme.secondary; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        VButton { visible: card.item.state === "draft" && page.documents.canMerge; text: "上移"; quiet: true; enabled: card.index > 0; onClicked: page.documents.move(card.item.id,-1) }
                        VButton { visible: card.item.state === "draft" && page.documents.canMerge; text: "下移"; quiet: true; enabled: card.index < page.documents.count-1; onClicked: page.documents.move(card.item.id,1) }
                        VButton { visible: card.item.state === "completed"; text: card.item.directory ? "查看圖片" : "開啟結果"; glyph: "folder"; onClicked: page.documents.openResult(card.item.id) }
                        VButton { visible: card.item.state === "failed" || card.item.state === "cancelled"; text: "重新準備"; onClicked: page.documents.retry(card.item.id) }
                        VButton { visible: card.item.active; text: "停止"; enabled: card.item.state !== "cancelling"; quiet: true; onClicked: page.documents.cancel(card.item.id) }
                        VButton { visible: !card.item.active; text: "移除"; quiet: true; onClicked: page.documents.remove(card.item.id) }
                    }
                }
            }
        }
        Text {
            Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.bottomMargin: 28
            text: "不支援 PDF 轉 Word、OCR、加密文件或巨集。PDF／圖片最多 200 頁；純文字上限 10 MB。"
            color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
        }
    }
}
