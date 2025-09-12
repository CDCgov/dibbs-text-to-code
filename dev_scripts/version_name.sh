#!/bin/sh
#
# Get the name of the version if the commit is tagged, else
# calculate the next feature version name for the project.
#
# Usage: dev_scripts/version_name.sh
#
# The format of the tag is vM.m.p or vM.m.p-rc.Z, where:
# - M is the major version
# - m is the minor version
# - p is the patch/bugfix version
# - Z is the number of commits on main since the last tag

HEAD_TAG=$(git describe --tags --exact-match HEAD 2>/dev/null)
# Check if the HEAD commit is tagged like '^v[0-9]+\.[0-9]+\.[0-9]+$'
if echo "$HEAD_TAG" | grep -q "^v[0-9]\+\.[0-9]\+\.[0-9]\+$"; then
  echo "$HEAD_TAG"
else
    # Get the latest tag
    latest_tag=$(git describe --tags --match "v*" --abbrev=0 "$(git rev-list --tags --max-count=1)" 2>/dev/null || echo "v0.0.0")
    # Get the next feature version
    next_ver=$(echo "$latest_tag" | awk -F. '{sub(/^v/, "", $1); $2++; print "v"$1"."$2".0"}')
    # Get the starting point for counting unreleased commits
    if [ "$latest_tag" != "v0.0.0" ]; then
        start="$latest_tag"
    else
        start=$(git rev-list --max-parents=0 HEAD)
    fi
    # Count the number of commits between the latest tag and HEAD
    commits=$(git rev-list --count "$start"..HEAD --)
    echo "${next_ver}-rc.${commits}"
fi
