#include <algorithm>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <iomanip>
#include <numeric>

using namespace std;

/*
 * Cloud Security Fundamentals
 *
 * A cloud security posture and threat assessment engine.
 *
 * Engineering focus:
 * - Typed cloud asset modeling
 * - Shared responsibility evaluation
 * - Attack surface analysis
 * - Threat detection
 * - IAM and network security evaluation
 * - Risk-based prioritization
 * - Security control enforcement
 * - Cloud asset lifecycle management
 */

enum class Provider {
    AWS,
    AZURE,
    GCP
};

enum class AssetType {
    COMPUTE,
    STORAGE,
    DATABASE,
    NETWORK,
    IDENTITY,
    SERVERLESS
};

enum class Severity {
    LOW = 1,
    MEDIUM = 2,
    HIGH = 3,
    CRITICAL = 4
};

enum class Responsibility {
    PROVIDER,
    CUSTOMER,
    SHARED
};

string toString(Provider provider) {
    switch (provider) {
        case Provider::AWS: return "AWS";
        case Provider::AZURE: return "AZURE";
        case Provider::GCP: return "GCP";
    }

    throw invalid_argument("Unknown provider.");
}

string toString(AssetType type) {
    switch (type) {
        case AssetType::COMPUTE: return "COMPUTE";
        case AssetType::STORAGE: return "STORAGE";
        case AssetType::DATABASE: return "DATABASE";
        case AssetType::NETWORK: return "NETWORK";
        case AssetType::IDENTITY: return "IDENTITY";
        case AssetType::SERVERLESS: return "SERVERLESS";
    }

    throw invalid_argument("Unknown asset type.");
}

string toString(Severity severity) {
    switch (severity) {
        case Severity::LOW: return "LOW";
        case Severity::MEDIUM: return "MEDIUM";
        case Severity::HIGH: return "HIGH";
        case Severity::CRITICAL: return "CRITICAL";
    }

    throw invalid_argument("Unknown severity.");
}

string toString(Responsibility responsibility) {
    switch (responsibility) {
        case Responsibility::PROVIDER: return "PROVIDER";
        case Responsibility::CUSTOMER: return "CUSTOMER";
        case Responsibility::SHARED: return "SHARED";
    }

    throw invalid_argument("Unknown responsibility.");
}

struct CloudAsset {
    string id;
    string name;
    Provider provider;
    AssetType type;
    string region;

    bool internetExposed = false;
    bool encryptionEnabled = true;
    bool tlsRequired = true;
    bool loggingEnabled = true;
    bool mfaEnabled = true;
    bool leastPrivilege = true;
    bool networkRestricted = true;
    bool backupEnabled = true;
    bool sensitiveData = false;
    bool active = true;

    set<string> permissions;

    void validate() const {
        if (id.empty() || name.empty() || region.empty()) {
            throw invalid_argument(
                "Asset ID, name and region are mandatory."
            );
        }

        for (const string& permission : permissions) {
            if (permission.empty()) {
                throw invalid_argument(
                    "Empty IAM permissions are invalid."
                );
            }
        }
    }
};

struct SecurityFinding {
    string assetId;
    string ruleId;
    string description;
    string remediation;
    Severity severity;
    Responsibility responsibility;
    int riskScore;
};

class ResponsibilityModel {
private:
    map<string, Responsibility> controls;

public:
    ResponsibilityModel() {
        controls = {
            {"physical_datacenter", Responsibility::PROVIDER},
            {"physical_network", Responsibility::PROVIDER},
            {"hypervisor", Responsibility::PROVIDER},
            {"guest_os", Responsibility::CUSTOMER},
            {"application", Responsibility::CUSTOMER},
            {"data", Responsibility::CUSTOMER},
            {"identity_access", Responsibility::CUSTOMER},
            {"network_configuration", Responsibility::CUSTOMER},
            {"managed_runtime", Responsibility::SHARED},
            {"security_monitoring", Responsibility::SHARED},
            {"incident_response", Responsibility::SHARED}
        };
    }

    Responsibility getOwner(const string& control) const {
        auto it = controls.find(control);

        if (it == controls.end()) {
            throw invalid_argument("Unknown security control.");
        }

        return it->second;
    }

    void display() const {
        cout << "\nSHARED RESPONSIBILITY MODEL\n";

        for (const auto& [control, owner] : controls) {
            cout << left << setw(25) << control
                 << toString(owner) << '\n';
        }
    }
};

class AttackSurface {
private:
    vector<string> exposedAssets;
    vector<string> identityAssets;
    vector<string> sensitiveAssets;
    vector<string> networkAssets;

public:
    void analyze(const vector<CloudAsset>& assets) {
        exposedAssets.clear();
        identityAssets.clear();
        sensitiveAssets.clear();
        networkAssets.clear();

        for (const auto& asset : assets) {
            if (!asset.active) {
                continue;
            }

            if (asset.internetExposed) {
                exposedAssets.push_back(asset.id);
            }

            if (asset.type == AssetType::IDENTITY) {
                identityAssets.push_back(asset.id);
            }

            if (asset.sensitiveData) {
                sensitiveAssets.push_back(asset.id);
            }

            if (asset.type == AssetType::NETWORK) {
                networkAssets.push_back(asset.id);
            }
        }
    }

    void display() const {
        auto show = [](const string& label,
                       const vector<string>& items) {
            cout << label << ": ";

            if (items.empty()) {
                cout << "None";
            }

            for (const auto& item : items) {
                cout << item << " ";
            }

            cout << '\n';
        };

        cout << "\nATTACK SURFACE ANALYSIS\n";

        show("Internet exposed", exposedAssets);
        show("Identity assets", identityAssets);
        show("Sensitive data", sensitiveAssets);
        show("Network boundaries", networkAssets);
    }
};

class CloudSecurityEngine {
private:
    map<string, CloudAsset> inventory;
    vector<SecurityFinding> findings;

    void addFinding(
        const CloudAsset& asset,
        const string& rule,
        const string& description,
        const string& remediation,
        Severity severity,
        int score
    ) {
        findings.push_back({
            asset.id,
            rule,
            description,
            remediation,
            severity,
            Responsibility::CUSTOMER,
            score
        });
    }

    void evaluate(const CloudAsset& asset) {
        if (!asset.active) {
            return;
        }

        if (
            asset.type == AssetType::STORAGE &&
            asset.internetExposed
        ) {
            addFinding(
                asset,
                "PUBLIC_STORAGE",
                "Storage is publicly accessible.",
                "Disable public access and enforce access policies.",
                Severity::CRITICAL,
                40
            );
        }

        if (
            asset.type == AssetType::DATABASE &&
            asset.internetExposed
        ) {
            addFinding(
                asset,
                "PUBLIC_DATABASE",
                "Database is internet accessible.",
                "Use private endpoints and network restrictions.",
                Severity::CRITICAL,
                40
            );
        }

        if (
            asset.sensitiveData &&
            !asset.encryptionEnabled
        ) {
            addFinding(
                asset,
                "UNENCRYPTED_DATA",
                "Sensitive information lacks encryption at rest.",
                "Enable encryption with managed encryption keys.",
                Severity::CRITICAL,
                35
            );
        }

        if (
            !asset.leastPrivilege ||
            asset.permissions.count("*") > 0
        ) {
            addFinding(
                asset,
                "EXCESSIVE_IAM",
                "IAM policy contains excessive permissions.",
                "Remove wildcard permissions and apply least privilege.",
                Severity::HIGH,
                25
            );
        }

        if (!asset.mfaEnabled) {
            addFinding(
                asset,
                "MFA_DISABLED",
                "Multi-factor authentication is disabled.",
                "Enforce MFA for privileged identities.",
                Severity::HIGH,
                25
            );
        }

        if (!asset.loggingEnabled) {
            addFinding(
                asset,
                "LOGGING_DISABLED",
                "Audit logging is disabled.",
                "Enable centralized and protected audit logging.",
                Severity::HIGH,
                20
            );
        }

        if (!asset.networkRestricted) {
            addFinding(
                asset,
                "OPEN_NETWORK",
                "Network access is insufficiently restricted.",
                "Implement segmentation and restrictive firewall rules.",
                Severity::HIGH,
                20
            );
        }

        if (!asset.tlsRequired) {
            addFinding(
                asset,
                "TLS_NOT_REQUIRED",
                "Secure transport is not enforced.",
                "Require TLS for data transmission.",
                Severity::HIGH,
                25
            );
        }

        if (!asset.backupEnabled) {
            addFinding(
                asset,
                "BACKUP_DISABLED",
                "Backup protection is disabled.",
                "Enable encrypted backups and test recovery.",
                Severity::MEDIUM,
                15
            );
        }
    }

public:
    void registerAsset(const CloudAsset& asset) {
        asset.validate();

        auto result = inventory.emplace(asset.id, asset);

        if (!result.second) {
            throw invalid_argument("Duplicate cloud asset ID.");
        }
    }

    vector<CloudAsset> getInventory() const {
        vector<CloudAsset> assets;

        for (const auto& [id, asset] : inventory) {
            assets.push_back(asset);
        }

        return assets;
    }

    void scan() {
        findings.clear();

        for (const auto& [id, asset] : inventory) {
            evaluate(asset);
        }

        sort(
            findings.begin(),
            findings.end(),
            [](const SecurityFinding& a,
               const SecurityFinding& b) {
                if (a.riskScore != b.riskScore) {
                    return a.riskScore > b.riskScore;
                }

                return a.assetId < b.assetId;
            }
        );
    }

    void displayFindings() const {
        cout << "\nSECURITY ASSESSMENT FINDINGS\n";

        if (findings.empty()) {
            cout << "No violations detected.\n";
            return;
        }

        for (const auto& finding : findings) {
            cout << "\n[" << toString(finding.severity) << "] "
                 << finding.ruleId
                 << "\nAsset: " << finding.assetId
                 << "\nRisk: " << finding.riskScore
                 << "\nResponsibility: "
                 << toString(finding.responsibility)
                 << "\nIssue: " << finding.description
                 << "\nRemediation: " << finding.remediation
                 << '\n';
        }
    }

    void displayStatistics() const {
        map<string, int> distribution = {
            {"CRITICAL", 0},
            {"HIGH", 0},
            {"MEDIUM", 0},
            {"LOW", 0}
        };

        int totalRisk = 0;

        for (const auto& finding : findings) {
            distribution[toString(finding.severity)]++;
            totalRisk += finding.riskScore;
        }

        cout << "\nSECURITY STATISTICS\n"
             << "Total assets: " << inventory.size()
             << "\nTotal findings: " << findings.size()
             << "\nTotal risk score: " << totalRisk << '\n';

        for (const auto& [severity, count] : distribution) {
            cout << severity << ": " << count << '\n';
        }
    }
};

void runTests() {
    ResponsibilityModel model;

    if (model.getOwner("data") != Responsibility::CUSTOMER) {
        throw runtime_error("Responsibility test failed.");
    }

    if (
        model.getOwner("hypervisor") != Responsibility::PROVIDER
    ) {
        throw runtime_error("Provider responsibility test failed.");
    }

    CloudSecurityEngine engine;

    CloudAsset asset{
        "TEST-001",
        "Test Storage",
        Provider::AWS,
        AssetType::STORAGE,
        "ap-south-1",
        true,
        false,
        true,
        false,
        false,
        false,
        false,
        false,
        true,
        true,
        {"*"}
    };

    engine.registerAsset(asset);
    engine.scan();

    auto inventory = engine.getInventory();

    if (inventory.size() != 1) {
        throw runtime_error("Inventory test failed.");
    }

    CloudAsset invalid = asset;
    invalid.id = "";

    try {
        invalid.validate();
        throw runtime_error("Invalid asset was accepted.");
    } catch (const invalid_argument&) {
        // Expected validation failure.
    }

    cout << "\nAll C++17 tests passed.\n";
}

int main() {
    try {
        cout << "CLOUD SECURITY FUNDAMENTALS\n";
        cout << "===========================\n";

        CloudSecurityEngine engine;

        CloudAsset storage{
            "AWS-S3-001",
            "Customer Documents",
            Provider::AWS,
            AssetType::STORAGE,
            "ap-south-1",
            true,
            false,
            true,
            false,
            false,
            false,
            false,
            false,
            true,
            true,
            {"*"}
        };

        CloudAsset compute{
            "AZURE-VM-001",
            "Application Server",
            Provider::AZURE,
            AssetType::COMPUTE,
            "centralindia",
            false,
            true,
            false,
            true,
            false,
            true,
            false,
            false,
            false,
            true,
            {"compute:read", "compute:write"}
        };

        CloudAsset database{
            "GCP-DB-001",
            "Production Database",
            Provider::GCP,
            AssetType::DATABASE,
            "asia-south1",
            true,
            true,
            true,
            true,
            true,
            true,
            true,
            false,
            true,
            true,
            {"database:read"}
        };

        engine.registerAsset(storage);
        engine.registerAsset(compute);
        engine.registerAsset(database);

        ResponsibilityModel responsibility;
        responsibility.display();

        AttackSurface surface;
        surface.analyze(engine.getInventory());
        surface.display();

        engine.scan();
        engine.displayFindings();
        engine.displayStatistics();

        runTests();

    } catch (const exception& error) {
        cerr << "Security engine failure: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}
