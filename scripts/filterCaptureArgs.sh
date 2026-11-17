#!/bin/bash
# Drop settings allsky.sh passes on the capture command line.
# Keep this pattern in sync with the historical allsky.sh filter, including
# the single alternative "^debuglevel=^cmd=" (there is no pipe between them).
grep -E -i -v '^config=|^debuglevel=^cmd=|^cameramodel|^cameranumber|^locale='
