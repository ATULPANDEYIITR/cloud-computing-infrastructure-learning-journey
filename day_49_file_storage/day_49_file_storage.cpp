#include <algorithm>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

class StorageException : public std::runtime_error {
public:
    explicit StorageException(const std::string& message)
        : std::runtime_error(message) {}
};

enum class NodeState {
    Online,
    Failed
};

struct Chunk {
    std::size_t index;
    std::string data;
    std::size_t checksum;
    std::vector<std::string> replicas;
};

struct FileMetadata {
    std::string path;
    std::size_t size{};
    std::vector<Chunk> chunks;
};

class StorageNode {
private:
    std::string name_;
    NodeState state_{NodeState::Online};
    std::unordered_map<std::string, std::string> chunks_;

public:
    explicit StorageNode(std::string name)
        : name_(std::move(name)) {}

    const std::string& name() const {
        return name_;
    }

    NodeState state() const {
        return state_;
    }

    void fail() {
        state_ = NodeState::Failed;
    }

    bool hasChunk(const std::string& key) const {
        return state_ == NodeState::Online &&
               chunks_.find(key) != chunks_.end();
    }

    void storeChunk(const std::string& key, const std::string& data) {
        if (state_ == NodeState::Failed) {
            throw StorageException("Cannot write to failed node " + name_);
        }

        chunks_[key] = data;
    }

    const std::string& readChunk(const std::string& key) const {
        auto iterator = chunks_.find(key);

        if (state_ == NodeState::Failed || iterator == chunks_.end()) {
            throw StorageException("Chunk unavailable on " + name_);
        }

        return iterator->second;
    }
};

class DistributedFileSystem {
private:
    std::map<std::string, StorageNode> nodes_;
    std::map<std::string, FileMetadata> files_;
    std::size_t chunkSize_;
    std::size_t replicationFactor_;

    static std::size_t checksum(const std::string& value) {
        return std::hash<std::string>{}(value);
    }

    std::vector<std::string> chooseReplicaNodes(std::size_t chunkIndex) const {
        if (nodes_.size() < replicationFactor_) {
            throw StorageException("Not enough storage nodes for replication");
        }

        std::vector<std::string> names;
        for (const auto& [name, node] : nodes_) {
            if (node.state() == NodeState::Online) {
                names.push_back(name);
            }
        }

        if (names.size() < replicationFactor_) {
            throw StorageException("Insufficient online nodes");
        }

        std::vector<std::string> result;
        const std::size_t start = chunkIndex % names.size();

        for (std::size_t offset = 0;
             offset < names.size() && result.size() < replicationFactor_;
             ++offset) {
            result.push_back(names[(start + offset) % names.size()]);
        }

        return result;
    }

public:
    DistributedFileSystem(
        std::vector<std::string> nodeNames,
        std::size_t chunkSize,
        std::size_t replicationFactor)
        : chunkSize_(chunkSize),
          replicationFactor_(replicationFactor) {

        if (chunkSize == 0) {
            throw std::invalid_argument("Chunk size must be positive");
        }

        if (replicationFactor == 0) {
            throw std::invalid_argument("Replication factor must be positive");
        }

        for (const auto& name : nodeNames) {
            nodes_.emplace(name, StorageNode(name));
        }

        if (nodes_.empty() || replicationFactor_ > nodes_.size()) {
            throw std::invalid_argument("Invalid distributed storage topology");
        }
    }

    void store(const std::string& path, const std::string& data) {
        if (path.empty()) {
            throw std::invalid_argument("File path cannot be empty");
        }

        FileMetadata metadata;
        metadata.path = path;
        metadata.size = data.size();

        std::size_t offset = 0;
        std::size_t chunkIndex = 0;

        do {
            const std::size_t length =
                std::min(chunkSize_, data.size() - offset);

            const std::string chunkData = data.substr(offset, length);
            const std::string key =
                path + "#" + std::to_string(chunkIndex);

            Chunk chunk{
                chunkIndex,
                chunkData,
                checksum(chunkData),
                chooseReplicaNodes(chunkIndex)
            };

            for (const auto& nodeName : chunk.replicas) {
                nodes_.at(nodeName).storeChunk(key, chunkData);
            }

            metadata.chunks.push_back(std::move(chunk));

            offset += length;
            ++chunkIndex;

        } while (offset < data.size() || data.empty() && chunkIndex == 0);

        files_[path] = std::move(metadata);
    }

    std::string read(const std::string& path) const {
        auto fileIterator = files_.find(path);

        if (fileIterator == files_.end()) {
            throw StorageException("File not found: " + path);
        }

        std::ostringstream result;

        for (const auto& chunk : fileIterator->second.chunks) {
            const std::string key =
                path + "#" + std::to_string(chunk.index);

            bool recovered = false;

            for (const auto& nodeName : chunk.replicas) {
                auto nodeIterator = nodes_.find(nodeName);

                if (nodeIterator == nodes_.end()) {
                    continue;
                }

                const StorageNode& node = nodeIterator->second;

                if (!node.hasChunk(key)) {
                    continue;
                }

                const std::string& content = node.readChunk(key);

                if (checksum(content) != chunk.checksum) {
                    throw StorageException(
                        "Checksum mismatch for chunk " +
                        std::to_string(chunk.index));
                }

                result << content;
                recovered = true;
                break;
            }

            if (!recovered) {
                throw StorageException(
                    "No healthy replica exists for chunk " +
                    std::to_string(chunk.index));
            }
        }

        return result.str();
    }

    void failNode(const std::string& nodeName) {
        nodes_.at(nodeName).fail();
    }

    bool isReadable(const std::string& path) const {
        try {
            static_cast<void>(read(path));
            return true;
        } catch (const StorageException&) {
            return false;
        }
    }

    void printPlacement(const std::string& path) const {
        const auto& metadata = files_.at(path);

        for (const auto& chunk : metadata.chunks) {
            std::cout << "Chunk " << chunk.index << " replicas: ";

            for (const auto& nodeName : chunk.replicas) {
                const auto& node = nodes_.at(nodeName);

                std::cout << nodeName << "="
                          << (node.state() == NodeState::Online
                                  ? "online"
                                  : "failed")
                          << " ";
            }

            std::cout << '\n';
        }
    }
};

class NetworkFileShare {
private:
    std::map<std::string, std::string> files_;

public:
    void write(const std::string& path, const std::string& data) {
        if (path.empty()) {
            throw StorageException("Network path cannot be empty");
        }

        files_[path] = data;
    }

    std::string read(const std::string& path) const {
        auto iterator = files_.find(path);

        if (iterator == files_.end()) {
            throw StorageException("Remote file does not exist");
        }

        return iterator->second;
    }

    void remove(const std::string& path) {
        if (files_.erase(path) == 0) {
            throw StorageException("Remote file does not exist");
        }
    }
};

int main() {
    try {
        std::cout << "=== Network file share ===\n";

        NetworkFileShare share;
        share.write(
            "/engineering/design.txt",
            "A network file system presents a shared remote namespace.");

        std::cout << share.read("/engineering/design.txt") << '\n';

        share.remove("/engineering/design.txt");

        std::cout << "\n=== Distributed file system case study ===\n";

        DistributedFileSystem dfs(
            {"node-a", "node-b", "node-c", "node-d"},
            16,
            2);

        const std::string dataset =
            "A distributed file system divides files into independently "
            "managed chunks and places replicas across multiple storage "
            "nodes. Replication allows a file to remain readable after "
            "a subset of storage nodes fails.";

        dfs.store("/datasets/operations.txt", dataset);

        std::cout << "Initial placement:\n";
        dfs.printPlacement("/datasets/operations.txt");

        std::cout << "\nReadable before failure: "
                  << std::boolalpha
                  << dfs.isReadable("/datasets/operations.txt")
                  << '\n';

        dfs.failNode("node-a");

        std::cout << "\nAfter node-a failure:\n";
        dfs.printPlacement("/datasets/operations.txt");

        std::cout << "Readable after one node failure: "
                  << dfs.isReadable("/datasets/operations.txt")
                  << '\n';

        const std::string recovered =
            dfs.read("/datasets/operations.txt");

        std::cout << "Recovered byte count: "
                  << recovered.size() << '\n';

        dfs.failNode("node-b");

        std::cout << "Readable after two related replica failures: "
                  << dfs.isReadable("/datasets/operations.txt")
                  << '\n';

        std::cout << "\nThe case study demonstrates why replication factor "
                     "and replica placement directly affect fault tolerance."
                  << '\n';

    } catch (const std::exception& error) {
        std::cerr << "Storage system error: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}
