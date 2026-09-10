#!/bin/bash
# Read Dependabot's head commit metadata; unknown update types fail closed.
set -euo pipefail
trap 'printf "%s\n" "deny: internal error"; exit 2' ERR

message=$(cat)
in_block=false
found_type=false
unsupported_type=false
block_pattern='^updated-dependencies:[[:space:]]*$'
type_pattern='^[[:space:]]*(-[[:space:]]+)?update-type:[[:space:]]*(.*)$'
allowed_pattern='^version-update:semver-(patch|minor)[[:space:]]*$'

while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$in_block" == false ]]; then
    if [[ "$line" =~ $block_pattern ]]; then
      in_block=true
    fi
    continue
  fi

  [[ "$line" == '...' ]] && break
  if [[ "$line" =~ $type_pattern ]]; then
    found_type=true
    value=${BASH_REMATCH[2]}
    if [[ ! "$value" =~ $allowed_pattern ]]; then
      unsupported_type=true
    fi
  fi
done <<< "$message"

if [[ "$in_block" == false ]]; then
  printf '%s\n' 'deny: missing updated-dependencies block'
elif [[ "$found_type" == false ]]; then
  printf '%s\n' 'deny: no update-type values'
elif [[ "$unsupported_type" == true ]]; then
  printf '%s\n' 'deny: unsupported update-type'
else
  printf '%s\n' 'allow'
fi
