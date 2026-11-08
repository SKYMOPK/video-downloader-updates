import QtQuick
Image {
    property string name: "download"
    source: name ? "../assets/icons/" + name + ".svg" : ""
    sourceSize: Qt.size(24, 24)
    width: 20; height: 20
    fillMode: Image.PreserveAspectFit
    opacity: enabled ? 1 : 0.4
}
