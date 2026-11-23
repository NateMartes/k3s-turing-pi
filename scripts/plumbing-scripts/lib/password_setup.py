#!/usr/bin/env python3

WORDS = (
    "Abalone Accordion Adventure Airplane Albatross Alligator Amethyst Antelope "
    "Apricot Aquarium Armadillo Arrowhead Asteroid Atlantic Avalanche Backpack "
    "Badminton Balloon Baritone Baseball Basilisk Battery Beehive Bellflower "
    "Birchwood Blackberry Blueberry Boardwalk Bonfire Bookcase Botanical Boulevard "
    "Breakfast Butterfly Cabbage Calendar Cardinal Carousel Carpenter Cascade "
    "Cathedral Cedarwood Celestial Chameleon Chestnut Cinnamon Clarinet Cloudburst "
    "Coconut Cometary Compass Constellation Cornflower Cranberry Crystal Cucumber "
    "Cupboard Cyclone Daffodil Daybreak Diamond Dinosaur Dolphin Dragonfly Dreamland "
    "Driftwood Earthworm Eclipse Elephant Emerald Evergreen Festival Firefly Flamingo "
    "Football Fountain Foxglove Freesia Gazelle Geranium Giraffe Glacier Goldfish "
    "Grapefruit Grassland Greenhouse Harmonica Hazelnut Hedgehog Hemlock Highrise "
    "Hollyhock Honeybee Honeycomb Horizon Hummingbird Hurricane Hyacinth Inkstone "
    "Jackrabbit Jasmine Jellyfish Juniper Kangaroo Kestrel Keyboard Kingfisher Kitchen "
    "Kumquat Ladybird Lakeside Lantern Lavender Lemonade Leopard Lighthouse Lilypad "
    "Lobster Magnolia Mandolin Marigold Meadowlark Midnight Moonbeam Mountain Mushroom "
    "Narcissus Nautilus Necklace Nightfall Notebook Oceanic Octopus Oleander Orchard "
    "Origami Paintbrush Pancake Panther Paprika Paradise Parakeet Peacock Peppermint "
    "Pineapple Poinsettia Popcorn Porpoise Prairie Pumpkin Quicksand Rainbow Rainstorm "
    "Raspberry Redwood Reindeer Riverbank Rosemary Saffron Sandcastle Sapphire Seahorse "
    "Sequoia Skylight Snowball Snowflake Starfish Stargazer Sunflower Sunrise Sunshine "
    "Swallowtail Symphony Tangerine Telescope Tempest Thunder Tortoise Treasure Trillium"
).split()

SYMBOLS = "!@#$%&*+-_=?"
MIN_PASSWORD_LENGTH = 15

MIN_PASSWORD_WORD_COUNT = 180

_invalid_words = [
    word
    for word in WORDS
    if len(word) < 7 or not word.isalpha() or not word.istitle()
]
if len(WORDS) < MIN_PASSWORD_WORD_COUNT:
    raise RuntimeError(
        f"Password word list must contain at least {MIN_PASSWORD_WORD_COUNT} words."
    )
if len(set(WORDS)) != len(WORDS):
    raise RuntimeError("Password word list must not contain duplicates.")
if _invalid_words:
    raise RuntimeError(
        "Password words must be alphabetic, title-cased, and at least seven "
        f"characters long: {', '.join(_invalid_words)}"
    )
