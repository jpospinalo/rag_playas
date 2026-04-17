# ------------------------------------------------------------------------------
# AMI: Ubuntu Server 24.04 LTS (última versión disponible)
# ------------------------------------------------------------------------------
data "aws_ami" "ubuntu_24" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ------------------------------------------------------------------------------
# Security Groups
# ------------------------------------------------------------------------------
resource "aws_security_group" "chromadb" {
  name        = "${var.project}-chromadb"
  description = "Permite SSH y trafico ChromaDB (puerto 8000)"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "ChromaDB API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Salida sin restricciones"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project}-chromadb-sg"
  }
}

resource "aws_security_group" "ollama" {
  name        = "${var.project}-ollama"
  description = "Permite SSH y trafico Ollama (puerto 11434)"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Ollama API"
    from_port   = 11434
    to_port     = 11434
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Salida sin restricciones"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project}-ollama-sg"
  }
}

# ------------------------------------------------------------------------------
# EC2 Instances
# ------------------------------------------------------------------------------
resource "aws_instance" "chromadb" {
  ami                    = data.aws_ami.ubuntu_24.id
  instance_type          = "t3.medium"
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.chromadb.id]

  root_block_device {
    volume_size = 12
    volume_type = "gp3"
  }

  user_data = file("${path.module}/../scripts/ec2_chroma_db.sh")

  tags = {
    Name = "${var.project}-chromadb"
  }
}

resource "aws_instance" "ollama" {
  ami                    = data.aws_ami.ubuntu_24.id
  instance_type          = "t3.large"
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.ollama.id]

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  user_data = file("${path.module}/../scripts/ec2_ollama_embeddings.sh")

  tags = {
    Name = "${var.project}-ollama"
  }
}

# ------------------------------------------------------------------------------
# Elastic IPs
# ------------------------------------------------------------------------------
resource "aws_eip" "chromadb" {
  domain = "vpc"

  tags = {
    Name = "${var.project}-chromadb-eip"
  }
}

resource "aws_eip" "ollama" {
  domain = "vpc"

  tags = {
    Name = "${var.project}-ollama-eip"
  }
}

# ------------------------------------------------------------------------------
# Asociaciones EIP ↔ Instancia
# ------------------------------------------------------------------------------
resource "aws_eip_association" "chromadb" {
  instance_id   = aws_instance.chromadb.id
  allocation_id = aws_eip.chromadb.id
}

resource "aws_eip_association" "ollama" {
  instance_id   = aws_instance.ollama.id
  allocation_id = aws_eip.ollama.id
}
