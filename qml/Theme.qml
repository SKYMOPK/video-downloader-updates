pragma Singleton
import QtQuick
QtObject {
    readonly property color bg: "#111315"
    readonly property color panel: "#191c20"
    readonly property color raised: "#24282e"
    readonly property color line: "#30353d"
    readonly property color text: "#f0f2f5"
    readonly property color secondary: "#a8b0bd"
    readonly property color muted: "#8a94a3"
    readonly property color accent: "#8bb9fa"
    readonly property color accentDark: "#182c46"
    readonly property color positive: "#86c8a3"
    readonly property color negative: "#f0a1a1"
    readonly property color warning: "#e6c28b"
    readonly property int radius: 12
    readonly property int duration: backend.reducedMotion ? 0 : 160
}
