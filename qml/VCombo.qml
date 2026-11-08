import QtQuick
import QtQuick.Controls
ComboBox {
    id: control
    implicitHeight: 42
    leftPadding: 12; rightPadding: 32
    font.pixelSize: 13
    background: Rectangle { color: control.enabled ? Theme.raised : "#202329"; radius: 8; border.width: control.activeFocus ? 2 : 1; border.color: control.activeFocus ? Theme.accent : Theme.line }
    contentItem: Text { text: control.displayText; color: control.enabled ? Theme.text : Theme.muted; font: control.font; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    indicator: Icon { name: "chevron-down"; x: control.width - width - 10; y: (control.height - height) / 2; width: 14; height: 14 }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: control.width
        height: 40
        highlighted: control.highlightedIndex === index
        contentItem: Text { text: modelData; color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: highlighted ? Theme.raised : Theme.panel; radius: 4 }
    }
    popup: Popup {
        y: control.height + 4
        width: control.width
        padding: 4
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 280)
        background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 8 }
        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: control.popup.visible ? control.delegateModel : null; currentIndex: control.highlightedIndex; ScrollIndicator.vertical: ScrollIndicator {} }
    }
}
