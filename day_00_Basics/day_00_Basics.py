# ============================================================
# DAY 00: CLOUD COMPUTING FUNDAMENTALS
# ============================================================

print("DAY 01 - CLOUD COMPUTING FUNDAMENTALS")


# ============================================================
# 1. WHAT IS CLOUD COMPUTING?
# ============================================================

print("\n1. WHAT IS CLOUD COMPUTING?")

print("Cloud computing is the delivery of computing resources")
print("such as servers, storage, databases, networking, and")
print("software over a network, usually the Internet.")

print("\nInstead of owning and maintaining all infrastructure,")
print("organizations can use computing resources when required.")


# ============================================================
# 2. BASIC CLOUD RESOURCES
# ============================================================

print("\n2. BASIC CLOUD RESOURCES")

cloud_resources = [
    "Compute",
    "Storage",
    "Databases",
    "Networking",
    "Security",
    "Applications"
]

for resource in cloud_resources:
    print("-", resource)


# ============================================================
# 3. COMPUTE
# ============================================================

print("\n3. COMPUTE")

compute = {
    "CPU": "Processes instructions",
    "Memory": "Temporarily stores data",
    "Server": "Runs applications"
}

for component, purpose in compute.items():
    print(component, "->", purpose)


# ============================================================
# 4. STORAGE
# ============================================================

print("\n4. STORAGE")

storage_types = [
    "Object Storage",
    "Block Storage",
    "File Storage"
]

for storage in storage_types:
    print("-", storage)


# ============================================================
# 5. CLOUD SERVICE MODELS
# ============================================================

print("\n5. CLOUD SERVICE MODELS")

service_models = {
    "IaaS": "Infrastructure as a Service",
    "PaaS": "Platform as a Service",
    "SaaS": "Software as a Service"
}

for model, meaning in service_models.items():
    print(model, "->", meaning)


# ============================================================
# 6. CLOUD DEPLOYMENT MODELS
# ============================================================

print("\n6. CLOUD DEPLOYMENT MODELS")

deployment_models = [
    "Public Cloud",
    "Private Cloud",
    "Hybrid Cloud"
]

for model in deployment_models:
    print("-", model)


# ============================================================
# 7. SCALABILITY
# ============================================================

print("\n7. SCALABILITY")

current_users = 1000
future_users = 100000

print("Current Users:", current_users)
print("Expected Users:", future_users)

print("\nScalability is the ability of a system")
print("to handle increasing workload or demand.")


# ============================================================
# 8. AVAILABILITY
# ============================================================

print("\n8. AVAILABILITY")

system_status = "Online"

print("System Status:", system_status)

print("\nAvailability refers to how consistently")
print("a system remains accessible and operational.")


# ============================================================
# 9. CLOUD REGIONS AND AVAILABILITY ZONES
# ============================================================

print("\n9. REGIONS AND AVAILABILITY ZONES")

region = "Example Region"
availability_zones = 3

print("Region:", region)
print("Availability Zones:", availability_zones)

print("\nCloud providers distribute infrastructure")
print("across geographic regions and isolated locations")
print("to improve resilience and availability.")


# ============================================================
# 10. PAY-AS-YOU-GO
# ============================================================

print("\n10. PAY-AS-YOU-GO")

hours_used = 10
cost_per_hour = 5

total_cost = hours_used * cost_per_hour

print("Hours Used:", hours_used)
print("Cost Per Hour: ₹", cost_per_hour)
print("Estimated Cost: ₹", total_cost)

print("\nCloud services commonly use usage-based pricing models.")


# ============================================================
# 11. CLOUD SECURITY
# ============================================================

print("\n11. CLOUD SECURITY")

security_controls = [
    "Identity and Access Management",
    "Authentication",
    "Authorization",
    "Encryption",
    "Network Security",
    "Monitoring"
]

for control in security_controls:
    print("-", control)


# ============================================================
# 12. BASIC CLOUD APPLICATION FLOW
# ============================================================

print("\n12. BASIC CLOUD APPLICATION FLOW")

print("""
User
  ↓
Internet
  ↓
Cloud Application
  ↓
Compute
  ↓
Database / Storage
  ↓
Response
  ↓
User
""")


# ============================================================
# 13. CLOUD BENEFITS
# ============================================================

print("\n13. BENEFITS OF CLOUD COMPUTING")

benefits = [
    "On-demand resources",
    "Scalability",
    "Flexibility",
    "Global availability",
    "Automation",
    "Reduced infrastructure management"
]

for benefit in benefits:
    print("-", benefit)


# ============================================================
# SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("DAY 01 COMPLETED")
print("=" * 60)

print("""
Today you learned:

1. What Cloud Computing is
2. Cloud resources
3. Compute
4. Storage
5. Cloud service models
6. Cloud deployment models
7. Scalability
8. Availability
9. Regions and Availability Zones
10. Pay-as-you-go
11. Cloud security
12. Basic cloud application flow
13. Benefits of cloud computing
""")
