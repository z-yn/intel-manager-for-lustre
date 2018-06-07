# vi: set ft=ruby :

require 'etc'
require "socket"

if ENV["JENKINS"] == "true"
	ci_cluster = true
	fqdn = Socket.gethostname
	dot = fqdn.index(".")
	hostname = fqdn[0..dot - 1]
	domain = fqdn[dot + 1..-1]
	mach_num = hostname[hostname.index("-") + 1..-1]
	cluster_num = 0
	if cluster_num == 0
		cluster_num_s = ""
	else
		cluster_num_s = cluster_num
	end
else
	ci_cluster = false
	hostname = ""
	cluster_num_s = ""
end

# Vagrant removed the atlas.hashicorp.com to vagrantcloud.com
# redirect. The value of DEFAULT_SERVER_URL in Vagrant versions
# less than 1.9.3 is atlas.hashicorp.com. This breaks the fetching
# and updating of boxes as they are now stored in
# vagrantcloud.com instead of atlas.hashicorp.com.
# https://github.com/hashicorp/vagrant/issues/9442
Vagrant::DEFAULT_SERVER_URL.replace('https://vagrantcloud.com')

Vagrant.configure("2") do |config|

	# Use box from Manager For Lustre project - this differs from the
	# "official" CentOS base box by using a SATA controller instead of IDE.
	# This simplifies the addition of extra disks for the storage servers.
	config.vm.box = "manager-for-lustre/centos73-1611-base"

	# no default sync'd folder
	config.vm.synced_folder ".", "/vagrant", disabled: true

	# Set the default RAM allocation for each VM.
	# 1GB is sufficient for demo and training purposes.
	# Admin server is allocated 2GB RAM.
	# Refer to the VM definition to change.
	config.vm.provider "virtualbox" do |vbx|
		vbx.memory = 2048
		vbx.cpus = 2
	end

	# Directory root for additional vdisks for MGT, MDT0, and OSTs
	# XXX It would be nice to put this in the above provider block since
	#     it really only applies for the vbox provider
	vdisk_root = "#{ENV['HOME']}/VirtualBox\ VMs/vdisks"

	config.vm.provider :libvirt do |libvirt, override|
		# prefix of what the VM will be named on the host
		libvirt.default_prefix = hostname
		# use the "images" storage pool
		libvirt.storage_pool_name = "images"
		# 2G of RAM and 2 CPUS
		libvirt.memory = 2048
		libvirt.cpus = 2
		override.vm.box = "centos/7"
		# set to distro version desired for test
		override.vm.box_version = "> 1804, < 9999"
	end

	# Number of shared disk devices
	sdnum=8

	# Hostname prefix for the cluster nodes
	# Example conventions:
	# ct<vmax><vmin>: CentOS <vmax>.<vmin>, e.g. ct73 = CentOS 7.3
	# rh<vmax><vmin>: RHEL <vmax>.<vmin>, e.g. rh73 = RHEL 7.3
	# el<vmax><vmin>: Generic RHEL derivative <vmax>.<vmin>,
	#	e.g. el73 = RHEL/CentOS 7.3
	# el<vmax>: Generic RHEL derivative <vmax>, e.g. el7 = RHEL/CentOS 7.x
	# sl<vmax><vmin>: SLES <vmax> SP<vmin>, e.g. sl121 = SLES 12 sp1
	# ub<vmax><vmin>: Ubuntu <vmax>.<vmin>, e.g. ub1604 = Ubuntu 16.04
	#
	# Each host in the virtual cluster will be automatically assigned
	# a name based on the prefix and the function of the host
	# The following examples are nodes running CentOS 7.3:
	# ct73-mds1 = 1st metadata server
	# ct73-oss3 = 3rd OSS
	# ct73-c2 = 2nd compute node
	host_prefix="ct7"
	# Create a set of /24 networks under a single /16 subnet range
	subnet_prefix="10.73"
	# Management network for admin comms
	mgmt_net_pfx="#{subnet_prefix}.10"
	# Lustre / HPC network
	lnet_pfx="#{subnet_prefix}.20"
	# Subnet index used to create cross-over nets for each HA cluster pair
	xnet_idx=230

	if ci_cluster
		# Vagrant (dumbly) adds the host's name to the loopback /etc/hosts
		# entry.  https://github.com/hashicorp/vagrant/issues/7263
		# They seem to be preferring simplicity-in-simple scnearios and
		# do really bad things to that end.  Things that blow up in real-
		# world complexity levels
	        config.vm.provision "fix /etc/hosts",
			type: "shell",
			inline: "sed -ie \"/^127.0.0.1/s/\$HOSTNAME  *//\" /etc/hosts /etc/hosts"
	else
		# Create a basic hosts file for the VMs.
		open('hosts', 'w') { |f|
		f.puts <<-__EOF
127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6

192.168.121.1 host
#{mgmt_net_pfx}.8 vm4
#{mgmt_net_pfx}.10 vm3
#{mgmt_net_pfx}.21 vm5
#{mgmt_net_pfx}.22 vm6
#{mgmt_net_pfx}.23 vm7
#{mgmt_net_pfx}.24 vm8
__EOF
		[2,9].each do |cidx|
			f.puts "#{mgmt_net_pfx}.3#{cidx} vm#{cidx}\n"
		end
		}
		config.vm.provision "file", source: "hosts", destination: "/tmp/hosts"
		config.vm.provision "shell", inline: "cp -f /tmp/hosts /etc/hosts"
	end
	config.vm.provision "shell", inline: "systemctl enable firewalld"
	config.vm.provision "shell", inline: "systemctl start firewalld"

	# Verbose booting
	config.vm.provision "shell", inline: "sed -ie 's/ rhgb quiet//' /boot/grub2/grub.cfg /etc/sysconfig/grub"

	# The VMs will have IPv6 but no IPv6 connectivity so alter
	# their gai.conf to prefer IPv4 addresses over IPv6
	config.vm.provision "shell", inline: "echo \"precedence ::ffff:0:0/96  100\" > /etc/gai.conf"

	# A simple way to create a key that can be used to enable
	# SSH between the virtual guests.
	#
	# The private key is copied onto the root account of the
	# administration node and the public key is appended to the
	# authorized_keys file of the root account for all nodes
	# in the cluster.
	#
	# Shelling out may not be the most Vagrant-friendly means to
	# create this key but it avoids more complex methods such as
	# developing a plugin.
	#
	# Popen may be a more secure way to exec but is more code
	# for what is, in this case, a relatively small gain.
	if not(File.exist?("id_rsa"))
		res = system("ssh-keygen -t rsa -N '' -f id_rsa -C \"IML Vagrant cluster\"")
	end

	# Add the generated SSH public key to each host's
	# authorized_keys file.
	config.vm.provision "file", source: "id_rsa.pub", destination: "/tmp/id_rsa.pub"
        if File.exist?("site-authorized_keys")
		config.vm.provision "file", source: "site-authorized_keys", destination: "/tmp/authorized_keys"
	end
	config.vm.provision "shell", inline: "mkdir -m 0700 -p /root/.ssh; if [ -f /tmp/id_rsa.pub ] && ! grep -q -f /tmp/id_rsa.pub; then cat /tmp/id_rsa.pub >&2; cat /tmp/id_rsa.pub >> /root/.ssh/authorized_keys; fi; cat /home/vagrant/.ssh/authorized_keys /tmp/authorized_keys >> /root/.ssh/authorized_keys; chmod 0600 /root/.ssh/authorized_keys; cat /root/.ssh/authorized_keys >&2"

	# And make the private key available
	config.vm.provision "file", source: "id_rsa", destination: "/tmp/id_rsa"
	config.vm.provision "shell", inline: "mkdir -m 0700 -p /root/.ssh; cp /tmp/id_rsa /root/.ssh/.; chmod 0600 /root/.ssh/id_rsa"

	if ci_cluster
		# delete default gw on eth0
		config.vm.provision "remove eth0 default route",
			type: "shell",
			run: "always",
			inline: "ip route del $(ip route ls | grep \"default via .* dev eth0\"); \
			         echo \"DEFROUTE=no\" >> /etc/sysconfig/network-scripts/ifcfg-eth0"
	end

	# The test framework needs an ssh_config file if not sshing to
	# the host machine as root
	open('ssh_config', 'w') { |f|
	f.puts <<-__EOF
Host host
  User #{Etc.getlogin}
  StrictHostKeyChecking no

Host #{hostname} vmhost
  User #{ENV['USER']}
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}2
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}3
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}4
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}5
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}6
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}7
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}8
  StrictHostKeyChecking no

Host #{hostname}vm#{cluster_num_s}9
  StrictHostKeyChecking no
__EOF
	}
	config.vm.provision "file", source: "ssh_config", destination: "/tmp/ssh_config"
	config.vm.provision "shell", inline: "cp /tmp/ssh_config /root/.ssh/config"


	#
	# Create an admin server for the cluster
	#
	config.vm.define "vm3", primary: true do |vm3|
		vm3.vm.provider "virtualbox" do |v|
			v.memory = 2048
		end
		vm3.vm.host_name = "#{hostname}vm#{cluster_num_s}3"
		vm3.vm.network "forwarded_port", guest: 443, host: 8443
		# Admin / management network
		if ci_cluster
			vm3.vm.network "public_network",
			    :libvirt__dhcp_enabled => false,
			    :type => 'bridge',
			    :dev => 'br0',
			    :mac => "525400%02dD9%d3" % [mach_num, cluster_num]
		else
			vm3.vm.network "private_network",
				ip: "#{mgmt_net_pfx}.10",
				netmask: "255.255.255.0"
		end
	end

	#
	# Create a test runner for the cluster
	#
	config.vm.define "vm4" do |vm4|
		vm4.vm.provider "virtualbox" do |v|
			v.memory = 2048
		end
		vm4.vm.host_name = "#{hostname}vm#{cluster_num_s}4"
		# Admin / management network
		if ci_cluster
			vm4.vm.network "public_network",
			    :libvirt__dhcp_enabled => false,
			    :type => 'bridge',
			    :dev => 'br0',
			    :mac => "525400%02dD9%d4" % [mach_num, cluster_num]
		else
			vm4.vm.network "private_network",
				ip: "#{mgmt_net_pfx}.8",
				netmask: "255.255.255.0"
		end
	end

	#
	# Create the storage servers (MDS, MGS and OSS)
	# Servers are configured in HA pairs
	#
	(1..4).each do |ss_idx|
		vm_num = ss_idx + 4
		config.vm.define "vm#{vm_num}", autostart: true do |ss|
			# Create additional storage to be shared between
			# the object storage server VMs.
			# Storage services associated with these #{vdisk_root}
			# will be maintained using HA failover.
			ss.vm.provider "virtualbox" do |vbx|
				# Set the target index range based on the node number.
				# Each SS is one of a pair, but will share these devices
				# Equation assumes that SSs are allocated in pairs with
				# consecutive numbering.
				osd_min = 1
				osd_max = osd_min + 7
				# Create the virtual disks for the targets
				# Only create the vdisks on odd-numbered VMs
				if ss_idx == 1
					(osd_min..osd_max).each do |target|
						if not(File.exist?("#{vdisk_root}/target#{target}.vdi"))
							vbx.customize ["createmedium", "disk",
								"--filename",
								  "#{vdisk_root}/target#{target}.vdi",
								"--size", "5120",
								"--format", "VDI",
								"--variant", "fixed"
								]
						end
					end
				end

				# Attach the vdisks to each OSS in the pair
				(osd_min..osd_max).each do |osd|
					pnum = (osd % sdnum) + 1
					vbx.customize ["storageattach", :id,
						"--storagectl", "SATA Controller",
						"--port", "#{pnum}",
						"--type", "hdd",
						"--medium", "#{vdisk_root}/target#{osd}.vdi",
						"--mtype", "shareable"
						]
				end
			end
			ss.vm.provider :libvirt do |libvirt|
				libvirt.disk_controller_model = "virtio-scsi"
				osd_min = 1
				osd_max = osd_min + 7
				(osd_min..osd_max).each do |target|
					libvirt.storage :file,
							:size => '5120M',
							:path => "target#{target}.img",
							:serial => "target#{target}",
							:allow_existing => true,
							:shareable => true,
							:bus => 'scsi',
							:cache => 'none',
							:type => 'raw'
				end
			end
			ss.vm.host_name = "#{hostname}vm#{cluster_num_s}#{vm_num}"
			# Admin / management network
			if ci_cluster
				ss.vm.network "public_network",
					:libvirt__dhcp_enabled => false,
					:type => 'bridge',
					:dev => 'br0',
					:mac => "525400%02dD9%d%d" % [mach_num, cluster_num, vm_num]
			else
				ss.vm.network "private_network",
					ip: "#{mgmt_net_pfx}.2#{ss_idx}",
					netmask: "255.255.255.0"
			end
			# Lustre / application network
			ss.vm.network "private_network",
				ip: "#{lnet_pfx}.2#{ss_idx}",
				netmask: "255.255.255.0"
			# Private network to simulate crossover.
			# Used exclusively as additional cluster network
			ss.vm.network "private_network",
				ip: "#{subnet_prefix}.#{xnet_idx}.2#{ss_idx}",
				netmask: "255.255.255.0",
				libvirt__dhcp_enabled: false,
				auto_config: false

			# Increment the "crossover" subnet number so that
			# each HA pair has a unique "crossover" subnet
			if ss_idx % 2 == 0
				xnet_idx+=1
			end
		config.vm.provision "shell", inline: "sed -i -e '/PasswordAuthentication no/s/no/yes/' /etc/ssh/sshd_config"
		end
	end

	# Create a set of compute nodes.
	# By default, only 2 compute nodes are created.
	# The configuration supports a maximum of 8 compute nodes.
	[2,9].each do |c_idx|
		config.vm.define "vm#{c_idx}", autostart: true do |c|
			c.vm.host_name = "#{hostname}vm#{cluster_num_s}#{c_idx}"
			# Admin / management network
			if ci_cluster
				c.vm.network "public_network",
					:libvirt__dhcp_enabled => false,
					:type => 'bridge',
					:dev => 'br0',
					:mac => "525400%02dD9%d%d" % [mach_num, cluster_num, c_idx]
			else
				c.vm.network "private_network",
					ip: "#{mgmt_net_pfx}.3#{c_idx}",
					netmask: "255.255.255.0"
			end
			# Lustre / application network
			c.vm.network "private_network",
				ip: "#{lnet_pfx}.3#{c_idx}",
				netmask: "255.255.255.0"
		end
	end
end
