import QtQuick
import QtQuick.Controls
Button {
    id: control
    property bool primary: false
    property bool quiet: false
    property bool selected: false
    property string glyph: ""
    implicitHeight: 40
    implicitWidth: Math.max(40, contentItem.implicitWidth + 28)
    leftPadding: 14; rightPadding: 14
    hoverEnabled: true
    font.pixelSize: 13
    Accessible.name: text
    background: Rectangle {
        radius: 8
        color: !control.enabled ? Theme.raised : control.primary ? (control.down ? "#77a7eb" : control.hovered ? "#a4caff" : Theme.accent) : control.down ? "#313741" : control.selected ? "#303a48" : control.hovered ? "#2b3038" : control.quiet ? "transparent" : Theme.raised
        border.width: control.activeFocus ? 2 : (control.primary || control.quiet ? 0 : 1)
        border.color: control.activeFocus ? Theme.accent : Theme.line
        Behavior on color { ColorAnimation { duration: Theme.duration } }
    }
    contentItem: Row {
        spacing: 8
        Icon { name: control.glyph; visible: control.glyph !== ""; anchors.verticalCenter: parent.verticalCenter; width: 16; height: 16; opacity: control.primary ? 0.8 : 1 }
        Text { text: control.text; color: !control.enabled ? Theme.muted : control.primary ? "#10223a" : control.selected ? Theme.accent : Theme.text; font: control.font; anchors.verticalCenter: parent.verticalCenter }
    }
    ToolTip.visible: hovered && text.length > 18
    ToolTip.text: text
}
