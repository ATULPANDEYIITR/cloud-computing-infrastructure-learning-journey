#include <algorithm>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

enum class TransactionState {
    Active,
    Committed,
    RolledBack
};

class ConstraintViolation : public std::runtime_error {
public:
    explicit ConstraintViolation(const std::string& message)
        : std::runtime_error(message) {}
};

class TransactionFailure : public std::runtime_error {
public:
    explicit TransactionFailure(const std::string& message)
        : std::runtime_error(message) {}
};

struct User {
    int id;
    std::string username;
};

struct Account {
    int id;
    int ownerId;
    std::int64_t balanceCents;
    std::uint64_t version;
};

struct Branch {
    std::string name;
    std::string headCommit;
    bool protectedBranch;
};

struct Repository {
    int id;
    std::string name;
    std::vector<Branch> branches;
};

class Database {
private:
    std::unordered_map<int, User> users_;
    std::unordered_map<int, Account> accounts_;
    int nextUserId_ = 1;
    int nextAccountId_ = 1;

public:
    const User& addUser(const std::string& username) {
        if (username.empty()) {
            throw ConstraintViolation("Username cannot be empty.");
        }

        const auto duplicate = std::find_if(
            users_.begin(),
            users_.end(),
            [&](const auto& item) {
                return item.second.username == username;
            }
        );

        if (duplicate != users_.end()) {
            throw ConstraintViolation("Username must be unique.");
        }

        const int id = nextUserId_++;
        auto [iterator, inserted] = users_.emplace(
            id,
            User{id, username}
        );

        if (!inserted) {
            throw TransactionFailure("Unable to create user.");
        }

        return iterator->second;
    }

    const Account& addAccount(int ownerId, std::int64_t balanceCents) {
        if (!users_.contains(ownerId)) {
            throw ConstraintViolation("Foreign-key owner does not exist.");
        }

        if (balanceCents < 0) {
            throw ConstraintViolation("Balance cannot be negative.");
        }

        const int id = nextAccountId_++;
        auto [iterator, inserted] = accounts_.emplace(
            id,
            Account{id, ownerId, balanceCents, 0}
        );

        if (!inserted) {
            throw TransactionFailure("Unable to create account.");
        }

        return iterator->second;
    }

    Account& account(int id) {
        auto iterator = accounts_.find(id);

        if (iterator == accounts_.end()) {
            throw ConstraintViolation("Account does not exist.");
        }

        return iterator->second;
    }

    const std::unordered_map<int, Account>& accounts() const {
        return accounts_;
    }
};

class Transaction {
private:
    Database& database_;
    TransactionState state_ = TransactionState::Active;

    struct StagedAccount {
        Account value;
        std::uint64_t originalVersion;
    };

    std::unordered_map<int, StagedAccount> staged_;

public:
    explicit Transaction(Database& database)
        : database_(database) {
        for (const auto& [id, account] : database.accounts()) {
            staged_.emplace(
                id,
                StagedAccount{account, account.version}
            );
        }
    }

    void requireActive() const {
        if (state_ != TransactionState::Active) {
            throw TransactionFailure("Transaction is no longer active.");
        }
    }

    void transfer(
        int sourceId,
        int destinationId,
        std::int64_t amountCents
    ) {
        requireActive();

        if (sourceId == destinationId) {
            throw ConstraintViolation(
                "Source and destination must differ."
            );
        }

        if (amountCents <= 0) {
            throw ConstraintViolation(
                "Transfer amount must be positive."
            );
        }

        auto source = staged_.find(sourceId);
        auto destination = staged_.find(destinationId);

        if (source == staged_.end() || destination == staged_.end()) {
            throw ConstraintViolation(
                "Both accounts must exist."
            );
        }

        if (source->second.value.balanceCents < amountCents) {
            throw ConstraintViolation(
                "Insufficient funds."
            );
        }

        source->second.value.balanceCents -= amountCents;
        destination->second.value.balanceCents += amountCents;
    }

    void commit() {
        requireActive();

        // Optimistic concurrency control protects against lost updates.
        for (const auto& [id, staged] : staged_) {
            Account& current = database_.account(id);

            if (current.version != staged.originalVersion) {
                throw TransactionFailure(
                    "Concurrent modification detected for account " +
                    std::to_string(id)
                );
            }
        }

        for (auto& [id, staged] : staged_) {
            Account& current = database_.account(id);

            if (current.balanceCents != staged.value.balanceCents) {
                current.balanceCents = staged.value.balanceCents;
                ++current.version;
            }
        }

        state_ = TransactionState::Committed;
    }

    void rollback() {
        requireActive();
        state_ = TransactionState::RolledBack;
    }
};

bool isMergeEligible(
    bool requiredChecksPassed,
    int approvals,
    int requiredApprovals,
    bool unresolvedConversations
) {
    if (!requiredChecksPassed) {
        return false;
    }

    if (approvals < requiredApprovals) {
        return false;
    }

    if (unresolvedConversations) {
        return false;
    }

    return true;
}

void printAccounts(const Database& database) {
    std::cout << "\nAccount state\n";

    for (const auto& [id, account] : database.accounts()) {
        std::cout
            << "Account " << id
            << " owner=" << account.ownerId
            << " balance=$"
            << std::fixed << std::setprecision(2)
            << static_cast<double>(account.balanceCents) / 100.0
            << " version=" << account.version
            << '\n';
    }
}

int main() {
    try {
        Database database;

        const User& alice = database.addUser("alice");
        const User& bob = database.addUser("bob");

        database.addAccount(alice.id, 10000);
        database.addAccount(bob.id, 2500);

        printAccounts(database);

        std::cout << "\nExecuting atomic transfer\n";

        Transaction transaction(database);
        transaction.transfer(1, 2, 3000);
        transaction.commit();

        printAccounts(database);

        std::cout << "\nTesting rollback\n";

        Transaction failedTransaction(database);

        try {
            failedTransaction.transfer(1, 2, 100000);
            failedTransaction.commit();
        } catch (const std::exception& error) {
            failedTransaction.rollback();
            std::cout << "Rejected: "
                      << error.what()
                      << '\n';
        }

        std::cout << "\nTesting relational constraints\n";

        try {
            database.addAccount(999, 100);
        } catch (const std::exception& error) {
            std::cout << "Foreign-key violation: "
                      << error.what()
                      << '\n';
        }

        try {
            database.addAccount(alice.id, -500);
        } catch (const std::exception& error) {
            std::cout << "Check violation: "
                      << error.what()
                      << '\n';
        }

        const bool eligible = isMergeEligible(
            true,
            2,
            2,
            false
        );

        std::cout
            << "\nGovernance decision: "
            << (eligible ? "eligible" : "blocked")
            << '\n';

        std::int64_t totalBalance = 0;

        for (const auto& [id, account] : database.accounts()) {
            totalBalance += account.balanceCents;
        }

        if (totalBalance != 12500) {
            throw TransactionFailure(
                "Accounting invariant violated."
            );
        }

        std::cout << "\nRelational architecture case study completed.\n";
        return 0;
    }
    catch (const std::exception& error) {
        std::cerr << "Fatal error: "
                  << error.what()
                  << '\n';
        return 1;
    }
}
