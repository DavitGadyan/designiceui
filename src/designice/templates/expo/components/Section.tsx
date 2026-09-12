import type { ReactNode } from "react";
import { View, StyleSheet } from "react-native";
import { theme } from "@/lib/theme";

/**
 * Vertical rhythm for the whole app. Alternate `tone` between neighbours so
 * the screen does not read as one long undifferentiated column - the phone
 * version of the eleven-identical-slabs problem.
 */
export function Section({
  children,
  tone = "ground",
}: {
  children: ReactNode;
  tone?: "ground" | "surface";
}) {
  return (
    <View
      style={[
        styles.section,
        { backgroundColor: tone === "surface" ? theme.colors.surface : theme.colors.ground },
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    paddingVertical: theme.spacing.section,
    paddingHorizontal: theme.spacing.gutter,
  },
});
