#!/bin/bash

set -e

# GNU coreutils stat quoting behavior
# need (escaped) double quotes for proper CSV parsing
export QUOTING_STYLE=c

scanner="${HOME}/bin/fsscan"

home_base="/volume1/data/downloads/(music)"
trees_path="${home_base}/catalogs/trees"
csvs_path="${trees_path}/csv"
state_path="${trees_path}/state"

if [ ! -d ${state_path} ]; then
  echo "# creating state path ${state_path}"
  mkdir -p "${state_path}"
fi

scan_tree_used() {
  local disk=$1
  local desc=$2
  local header=$3

  if [ -d "${disk}" ]; then
    local tree_file="${trees_path}/${desc}.tree"
    local csv_file="${csvs_path}/${desc}.csv"
    local state_file="${state_path}/${desc}.state"

    printf "\n#\n"
    printf "# cataloging %s\n" "${disk}"
    printf "#\n"

    printf "\n# creating tree file at %s\n" "${tree_file}"
    time {
      echo "${header}"
      echo
      tree -I "@eaDir" -N "${disk}"
      echo
      du -sm "${disk}"
    } >"${tree_file}"

    printf "\n# recreating CSV file at %s\n" "${csv_file}"
    time $scanner "${disk}" -s "${state_file}" -o "${csv_file}"
  else
    printf "\n%s must be available to catalog!\n" "${disk}"
  fi
}

scan_tree_df() {
  local disk=$1
  local desc=$2
  local header=$3

  if [ -d "${disk}" ]; then
    local tree_file="${trees_path}/${desc}.tree"
    local csv_file="${csvs_path}/${desc}.csv"
    local state_file="${state_path}/${desc}.state"

    printf "\n#\n"
    printf "# cataloging %s\n" "${disk}"
    printf "#\n"

    printf "\n# creating tree file at %s\n" "${tree_file}"
    time {
      echo "${header}"
      echo
      tree -I "@eaDir" -N "${disk}"
      echo
      df -PH "${disk}"
    } >"${tree_file}"

    printf "\n# recreating CSV file at %s\n" "${csv_file}"
    time $scanner "${disk}" -s "${state_file}" -o "${csv_file}"
  else
    printf "\n%s must be available to catalog!\n" "${disk}"
  fi
}

scan_tree_subs() {
  local disk=$1
  local desc=$2
  local header=$3

  if [ -d "${disk}" ]; then
    local tree_file="${trees_path}/${desc}.tree"
    local csv_file="${csvs_path}/${desc}.csv"
    local state_file="${state_path}/${desc}.state"

    printf "\n#\n"
    printf "# cataloging %s\n" "${disk}"
    printf "#\n"

    printf "\n# creating tree file at %s\n" "${tree_file}"
    time {
      echo "${header}"
      echo
      tree -I "@eaDir" -N "${disk}"
      echo
      df -PH "${disk}"
      echo
      du -sm "${disk}"/*
    } >"${tree_file}"

    printf "\n# recreating CSV file at %s\n" "${csv_file}"
    time $scanner "${disk}" -s "${state_file}" -o "${csv_file}"
  else
    printf "\n%s must be available to catalog!\n" "${disk}"
  fi
}

scan_tree_used \
  "/Users/ogd/Downloads/music" \
  "laptop music directory" \
  "local music processing directory"

scan_tree_subs \
  "/Volumes/XPHEAR" \
  "XPHEAR (2TB blue Seagate Backup Plus)" \
  "2TB blue Seagate Backup Plus HD formatted with APFS (offline music archive)"

scan_tree_df \
  "/volume1/data/backups/atropos" \
  "euterpe atropos (NAS directory)" \
  "2TB blue Seagate Backup Plus HD formatted with HFS+ (FLAC archive)"

scan_tree_df \
  "/volume1/data/video/Television" \
  "euterpe television (NAS directory)" \
  "Synology NAS //data/video/Television sharre"

scan_tree_df \
  "/volume1/data/video/Movies" \
  "euterpe movies (NAS directory)" \
  "Synology NAS //data/video/Movies"

scan_tree_df \
  "/volume1/video/anime" \
  "euterpe anime (NAS directory)" \
  "Synology NAS //video/anime"

scan_tree_subs \
  "/volume1/music" \
  "euterpe music (NAS volume)" \
  "Synology NAS //music"
