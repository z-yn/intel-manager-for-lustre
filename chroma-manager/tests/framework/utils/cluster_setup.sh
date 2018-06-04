# Remove test results and coverage reports from previous run
rm -rfv $PWD/test_reports/*
rm -rfv $PWD/coverage_reports/.coverage*
mkdir -p $PWD/test_reports
mkdir -p $PWD/coverage_reports

CLUSTER_CONFIG=${CLUSTER_CONFIG:-"$(ls $PWD/shared_storage_configuration_cluster_cfg.json)"}
CHROMA_DIR=${CHROMA_DIR:-"$PWD/intel-manager-for-lustre/"}
USE_FENCE_XVM=false

eval $(python $CHROMA_DIR/chroma-manager/tests/utils/json_cfg2sh.py "$CLUSTER_CONFIG")

MEASURE_COVERAGE=${MEASURE_COVERAGE:-true}
PROXY=${PROXY:-''} # Pass in a command that will set your proxy settings iff the cluster is behind a proxy. Ex: PROXY="http_proxy=foo https_proxy=foo"

echo "Beginning installation and setup..."

# put some keys on the nodes for easy access by developers
# and make sure EPEL is enabled
pdsh -l root -R ssh -S -w $(spacelist_to_commalist $ALL_NODES) "exec 2>&1; set -xe
if $JENKINS && ${VAGRANT:-false}; then
    cat <<\"EOF\" > /etc/profile.d/intel_proxy.sh
http_proxy=\"http://proxy.rr.intel.com:911\"
https_proxy=\"http://proxy.rr.intel.com:911\"
no_proxy=\".localdomain,intel.com,*.lotus.hpdd.lab.intel.com,*.iml.intel.com,*.intel.com,10.14.80.*,10.14.81.*,10.14.82.*,10.14.83.*,10.14.80.0/22,$server,jenkins,cobbler,127.0.0.1,localhost\",vm2,vm3,vm4,vm5,vm6,vm7,vm8,vm9
export http_proxy https_proxy no_proxy
EOF
    . /etc/profile.d/intel_proxy.sh

    rm -f /etc/yum.repos.d/*
    cat <<\"EOF\" > /etc/yum.repos.d/cobbler-config.repo
[core-0]
name=core-0
baseurl=http://cobbler/cobbler/ks_mirror/CentOS-7.5-x86_64
enabled=1
gpgcheck=0
priority=1


[updates-centos7.5-x86_64]
name=updates-centos7.5-x86_64
baseurl=http://cobbler/cobbler/repo_mirror/updates-centos7.5-x86_64
enabled=1
priority=1
gpgcheck=0


[local-toolkit_el7-x86_64]
name=local-toolkit_el7-x86_64
baseurl=http://cobbler/cobbler/repo_mirror/local-toolkit_el7-x86_64
enabled=1
priority=10
gpgcheck=0


[chef-stable-el7-x86_64]
name=chef-stable-el7-x86_64
baseurl=http://cobbler/cobbler/repo_mirror/chef-stable-el7-x86_64
enabled=1
priority=1
gpgcheck=0


[addon-epel7-x86_64]
name=addon-epel7-x86_64
baseurl=http://cobbler/cobbler/repo_mirror/addon-epel7-x86_64
enabled=1
priority=1
gpgcheck=0
EOF
fi

$LOCAL_CLUSTER_SETUP

# disable the toolkit repo
yum-config-manager --disable local-toolkit_el7-x86_64

cat <<\"EOF\" >> /root/.ssh/authorized_keys
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCrcI6x6Fv2nzJwXP5mtItOcIDVsiD0Y//LgzclhRPOT9PQ/jwhQJgrggPhYr5uIMgJ7szKTLDCNtPIXiBEkFiCf9jtGP9I6wat83r8g7tRCk7NVcMm0e0lWbidqpdqKdur9cTGSOSRMp7x4z8XB8tqs0lk3hWefQROkpojzSZE7fo/IT3WFQteMOj2yxiVZYFKJ5DvvjdN8M2Iw8UrFBUJuXv5CQ3xV66ZvIcYkth3keFk5ZjfsnDLS3N1lh1Noj8XbZFdSRC++nbWl1HfNitMRm/EBkRGVP3miWgVNfgyyaT9lzHbR8XA7td/fdE5XrTpc7Mu38PE7uuXyLcR4F7l brian@brian-laptop
EOF

# instruct any caching proxies to only cache packages
yum -y install ed
ed /etc/yum.conf <<EOF
/^$/i
http_caching=packages
.
wq
EOF

for key in CentOS-7 redhat-release; do
    if [ -f /etc/pki/rpm-gpg/RPM-GPG-KEY-\$key ]; then
        rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-\$key
    fi
done

if [ -n "$CLIENT_1" ] && [[ \${HOSTNAME%%%.*} = ${CLIENT_1%%.*} ]]; then
    yum-config-manager --add-repo "$LUSTRE_CLIENT_URL"
    sed -i -e '1d' -e \"2s/^.*$/[lustre-client]/\" -e '/baseurl/s/,/%2C/g' -e '/enabled/a gpgcheck=0' "$LUSTRE_CLIENT_REPO_FILE"
fi" | dshbak -c
if [ ${PIPESTATUS[0]} != 0 ]; then
    exit 1
fi
