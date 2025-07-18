This PR was opened automatically by the `charmed-analytics-ci` library as part of the Rock CI system after the rock image was built and published.

## 🔧 Updated Rock References

The following image paths were updated:


- **File**: `charms/charm1/metadata.yaml`
  - **Path**: `resources.kserve-controller-image.upstream-source`

- **File**: `charms/charm1/src/default-custom-images.json`
  - **Path**: `configmap__batcher`

- **File**: `charms/charm1/config.yaml`
  - **Path**: `options.no-proxy.default`





## ⚠️ Manual Action Required

The following service-spec files were **not found** in the repository and should be updated manually:


- **File**: `charms/charm1/service-spec-missing.yaml`
  
  - Manually set **user** to: `_daemon_`
  
  
  - Manually set **command** to: `f"bash -c '{self._exec_command}' new command"
`
