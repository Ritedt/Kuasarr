import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Edit2,
  Trash2,
  Folder,
  AlertCircle,
  Check,
  Tag,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Spinner } from '../components/ui/Spinner';
import { Modal } from '../components/ui/Modal';
import { Toggle } from '../components/ui/Toggle';
import { getCategories, createCategory, updateCategory, deleteCategory } from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type { Category, CreateCategoryRequest } from '../types';

interface CategoryFormData {
  name: string;
  pattern: string;
  priority: number;
  enabled: boolean;
}

const initialFormData: CategoryFormData = {
  name: '',
  pattern: '',
  priority: 0,
  enabled: true,
};

function CategoryRow({
  category,
  onEdit,
  onDelete,
  onToggleEnabled,
  isPending,
}: {
  category: Category;
  onEdit: (category: Category) => void;
  onDelete: (id: string) => void;
  onToggleEnabled: (id: string, enabled: boolean) => void;
  isPending: boolean;
}) {
  return (
    <div className="p-4 border-b border-bg-tertiary last:border-0 hover:bg-bg-tertiary/30 transition-colors">
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-kuasarr-primary/10 rounded-lg shrink-0">
            <Folder className="h-5 w-5 text-kuasarr-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-medium text-text-primary">{category.name}</h3>
              <Badge variant={category.enabled ? 'success' : 'default'} size="sm">
                {category.enabled ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-sm text-text-secondary mt-1 flex-wrap">
              <span className="font-mono text-xs bg-bg-tertiary px-2 py-0.5 rounded truncate max-w-[180px] sm:max-w-none">{category.pattern}</span>
              <span>Priority: {category.priority}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 pl-1">
          <Toggle
            checked={category.enabled}
            onChange={(checked) => onToggleEnabled(category.id, checked)}
            disabled={isPending}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onEdit(category)}
            disabled={isPending}
            leftIcon={<Edit2 className="h-4 w-4" />}
          >
            Edit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(category.id)}
            disabled={isPending}
            leftIcon={<Trash2 className="h-4 w-4 text-kuasarr-error" />}
          >
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function CategoriesPage() {
  const { jdConnected } = useUIStore();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [formData, setFormData] = useState<CategoryFormData>(initialFormData);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof CategoryFormData, string>>>({});

  const { data: categories = [], isLoading } = useQuery({
    queryKey: ['categories'],
    queryFn: getCategories,
  });

  const createMutation = useMutation({
    mutationFn: createCategory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Category> }) => updateCategory(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCategory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      setDeleteId(null);
    },
  });

  const validateForm = (): boolean => {
    const errors: Partial<Record<keyof CategoryFormData, string>> = {};

    if (!formData.name.trim()) {
      errors.name = 'Name is required';
    }
    if (!formData.pattern.trim()) {
      errors.pattern = 'Pattern is required';
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    const data: CreateCategoryRequest = {
      name: formData.name.trim(),
      pattern: formData.pattern.trim(),
      priority: formData.priority,
      enabled: formData.enabled,
    };

    if (editingCategory) {
      updateMutation.mutate({ id: editingCategory.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const handleEdit = (category: Category) => {
    setEditingCategory(category);
    setFormData({
      name: category.name,
      pattern: category.pattern,
      priority: category.priority,
      enabled: category.enabled,
    });
    setFormErrors({});
    setIsModalOpen(true);
  };

  const handleCreate = () => {
    setEditingCategory(null);
    setFormData(initialFormData);
    setFormErrors({});
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingCategory(null);
    setFormData(initialFormData);
    setFormErrors({});
  };

  const handleToggleEnabled = (id: string, enabled: boolean) => {
    updateMutation.mutate({ id, data: { enabled } });
  };

  const sortedCategories = [...categories].sort((a, b) => b.priority - a.priority);

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Categories</h1>
            <p className="text-text-secondary mt-1">Manage download categories and auto-sorting patterns</p>
          </div>
          <Button
            variant="primary"
            onClick={handleCreate}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Category
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Tag className="h-5 w-5" />
              Categories ({categories.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Spinner size="lg" />
              </div>
            ) : categories.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 px-4">
                <Folder className="h-12 w-12 text-text-secondary/50 mb-4" />
                <h3 className="text-lg font-medium text-text-primary">No Categories</h3>
                <p className="text-text-secondary text-sm mt-1 text-center max-w-md">
                  Categories help automatically sort downloads based on filename patterns. Create your first category to get started.
                </p>
                <Button variant="primary" className="mt-4" onClick={handleCreate} leftIcon={<Plus className="h-4 w-4" />}>
                  Add Category
                </Button>
              </div>
            ) : (
              sortedCategories.map((category) => (
                <CategoryRow
                  key={category.id}
                  category={category}
                  onEdit={handleEdit}
                  onDelete={setDeleteId}
                  onToggleEnabled={handleToggleEnabled}
                  isPending={updateMutation.isPending}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card className="bg-kuasarr-primary/5 border-kuasarr-primary/20">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-kuasarr-primary mt-0.5" />
              <div>
                <h4 className="font-medium text-text-primary">About Categories</h4>
                <p className="text-sm text-text-secondary mt-1">
                  Categories use regex patterns to automatically sort downloads. Higher priority categories are checked first.
                  Patterns are matched against download filenames to determine the appropriate category.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={closeModal}
        title={editingCategory ? 'Edit Category' : 'Create Category'}
        description={editingCategory ? 'Update category details and pattern' : 'Add a new category with auto-sorting pattern'}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Name"
            placeholder="e.g., Movies, TV Shows, Books"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            error={formErrors.name}
            required
          />
          <Input
            label="Pattern"
            placeholder="e.g., .*\\.(mkv|mp4)$ or (?i)movie"
            value={formData.pattern}
            onChange={(e) => setFormData({ ...formData, pattern: e.target.value })}
            error={formErrors.pattern}
            helperText="Regex pattern to match against filenames"
            required
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Priority"
              type="number"
              value={formData.priority.toString()}
              onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 0 })}
              helperText="Higher priority = checked first"
            />
            <div className="flex items-end">
              <Toggle
                label="Enabled"
                checked={formData.enabled}
                onChange={(checked) => setFormData({ ...formData, enabled: checked })}
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <Button type="button" variant="ghost" onClick={closeModal}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={createMutation.isPending || updateMutation.isPending}
              leftIcon={editingCategory ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            >
              {editingCategory ? 'Update' : 'Create'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        title="Delete Category"
        description="Are you sure you want to delete this category? This action cannot be undone."
      >
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="ghost" onClick={() => setDeleteId(null)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => deleteId && deleteMutation.mutate(deleteId)}
            loading={deleteMutation.isPending}
            leftIcon={<Trash2 className="h-4 w-4" />}
          >
            Delete
          </Button>
        </div>
      </Modal>
    </Layout>
  );
}
