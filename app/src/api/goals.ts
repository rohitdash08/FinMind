import axios from "axios";

const api = axios.create({
    baseURL: "/api/goals",
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem("token");
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export interface GoalMilestone {
    id: number;
    name: string;
    target_amount: number;
    achieved: boolean;
}

export interface Goal {
    id: number;
    name: string;
    target_amount: number;
    current_amount: number;
    currency: string;
    deadline: string | null;
    created_at: string;
    milestones: GoalMilestone[];
}

export const getGoals = async (): Promise<Goal[]> => {
    const response = await api.get("");
    return response.data;
};

export const createGoal = async (data: any) => {
    const response = await api.post("", data);
    return response.data;
};

export const updateGoal = async (id: number, data: any) => {
    const response = await api.put(`/${id}`, data);
    return response.data;
};

export const deleteGoal = async (id: number) => {
    const response = await api.delete(`/${id}`);
    return response.data;
};
