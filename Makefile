SRC_DIRS := operators panels properties utils wheels
ROOT_FILES := __init__.py LICENSE.txt blender_manifest.toml
EXCLUDE_FILES := .gitignore README.md
EXCLUDE_PATTERNS := __pycache__ *.pyc
BUILD_DIR := __build__/rendergate
RELEASES_DIR := __releases__
# Extract version from __init__.py
VERSION := $(shell python3 -c "import re; init_py=open('__init__.py').read(); version=re.search(r'\"version\": \((\d+), (\d+), (\d+)\)', init_py).groups(); print('.'.join(version))")
ZIP_FILE := ../__releases__/Rendergate\ v$(VERSION).zip


# default target
build-addon: clean setup copy zip

# clean build directory
clean:
	@rm -rf __build__

# create directories and subdirectories
setup:
	mkdir -p $(BUILD_DIR)
	mkdir -p $(RELEASES_DIR)
	for dir in $(SRC_DIRS); do \
		mkdir -p $(BUILD_DIR)/$$dir; \
	done

# copy files excluding some
copy:
	for dir in $(SRC_DIRS); do \
		for file in `find $$dir -type f ! -path "*/__pycache__/*" ! -name "*.pyc"`; do \
			filename=$$(basename $$file); \
			if ! echo $(EXCLUDE_FILES) | grep -q $$filename; then \
				cp $$file $(BUILD_DIR)/$$dir/; \
			fi; \
		done \
	done
	# Copy files from the root directory
	for file in $(ROOT_FILES); do \
		if [ -f $$file ]; then \
			cp $$file $(BUILD_DIR)/; \
		fi; \
	done

# zip the in release folder
zip:
	cd __build__ && zip -r $(ZIP_FILE) "rendergate"
