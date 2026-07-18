import xml.etree.ElementTree as ET

FET_FILE = "../EMAD_2627_.fet"


def read_fet():
    tree = ET.parse(FET_FILE)
    root = tree.getroot()

    print("\n=== FET ROOT ===")
    print(root.tag)

    print("\n=== SECCIONS PRINCIPALS ===")

    for child in root:
        print(f"- {child.tag}")

    print("\n=== RESUM D'ACTIVITIES (si existeix) ===")

    # intentar trobar activitats
    for child in root:
        if "activity" in child.tag.lower():
            print(child.tag)


if __name__ == "__main__":
    read_fet()